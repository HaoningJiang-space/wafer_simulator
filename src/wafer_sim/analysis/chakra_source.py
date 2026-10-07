"""Read-only source support inventory; never infer tensor versions from IDs.

CPU operators, GPU kernels and metadata remain separate. Captured durations
are evidence about the source, not target work or a time-to-FLOPs conversion.
"""
import ast
from collections import Counter
import graphlib
import json

from wafer_sim.workloads.chakra import read_metadata, nodes
from wafer_sim.workloads.chakra_work import matrix_work, transformer_engine_work


def decode_io(info):
    """Upstream writes Python list repr into IOInfo; accept literals only."""
    fields = []
    for key in ("values", "shapes", "types"):
        text = getattr(info, key)
        value = ast.literal_eval(text) if text else []
        if not isinstance(value, list):
            raise ValueError(f"Chakra IO {key} must be a list")
        fields.append(value)
    if len({len(v) for v in fields}) != 1:
        raise ValueError("Chakra IO values/shapes/types lengths disagree")
    return tuple(fields)


def attribute_values(message):
    result = {}
    for attr in message.attr:
        if attr.name in result:
            raise ValueError(f"Duplicate Chakra attribute: {attr.name}")
        field = attr.WhichOneof("value")
        if not field:
            raise ValueError(f"Unset Chakra attribute: {attr.name}")
        value = getattr(attr, field)
        result[attr.name] = list(value.values) if field.endswith("_list") else value
    return result


def graph_summary(predecessors):
    missing = sorted(set(p for deps in predecessors.values() for p in deps) - predecessors.keys())
    cycle = None
    if not missing:
        try:
            graphlib.TopologicalSorter(predecessors).prepare()
        except graphlib.CycleError as error:
            cycle = error.args[1]
    return dict(nodes=len(predecessors), unique_edges=sum(map(len, predecessors.values())),
                missing_count=len(missing), missing_examples=missing[:16],
                cycle_example=cycle[:16] if cycle else None,
                closed_acyclic=not missing and cycle is None)


def inspect_rank(path, schema):
    """Scan every byte/node, preserving separate control and data relations."""
    counts, attrs_count, names, collective = Counter(), Counter(), Counter(), Counter()
    dependencies, controls = {}, {}
    signatures = Counter()
    examples = {}
    min_start, max_end = None, 0
    work_records = []
    with path.open("rb") as stream:
        metadata = read_metadata(stream, schema)
        for offset, node in nodes(stream, schema):
            if node.id in dependencies:
                raise ValueError(f"Duplicate node ID {node.id} in {path}")
            if len(node.data_deps) != len(set(node.data_deps)) or len(node.ctrl_deps) != len(set(node.ctrl_deps)):
                raise ValueError(f"Duplicate source dependency in node {node.id}")
            dependencies[node.id] = set(node.data_deps)
            controls[node.id] = set(node.ctrl_deps)
            attributes = attribute_values(node)
            kind = schema.NodeType.Name(node.type)
            domain = "CPU" if attributes.get("is_cpu_op") is True else (
                "GPU" if attributes.get("is_cpu_op") is False else "unspecified")
            counts[f"nodes:{kind}:{domain}"] += 1
            attrs_count.update(attributes.keys())
            names[(kind, domain, node.name)] += 1
            for key in ("num_ops", "num_flops", "tensor_size", "comm_size", "comm_type"):
                if key in attributes:
                    counts[f"attribute_present:{key}"] += 1
            if "comm_type" in attributes:
                collective[str(attributes["comm_type"])] += 1
            if node.duration_micros:
                counts[f"nonzero_source_duration:{domain}"] += 1
            if node.start_time_micros:
                min_start = min(min_start or node.start_time_micros, node.start_time_micros)
                max_end = max(max_end, node.start_time_micros + node.duration_micros)
            # Detect wire fields newer than this schema instead of assuming they are absent.
            known = schema.Node(); known.CopyFrom(node); known.DiscardUnknownFields()
            counts["nodes_with_unknown_wire_fields"] += known.SerializeToString() != node.SerializeToString()
            parsed = {}
            for side in ("inputs", "outputs"):
                try:
                    parsed[side] = decode_io(getattr(node, side))
                except (ValueError, SyntaxError, TypeError, RecursionError):
                    counts[f"unparsed_io:{side}:{domain}"] += 1
                    parsed[side] = None
                if parsed[side] and parsed[side][0]:
                    counts[f"nonempty_io:{side}:{domain}"] += 1
            shape_key = tuple(json.dumps(parsed[s][1], separators=(",", ":")) if parsed[s] else "UNPARSED"
                              for s in ("inputs", "outputs"))
            signatures[(kind, domain, node.name, *shape_key)] += 1
            if domain == "CPU" and node.name in ("aten::mm", "aten::bmm", "tex_ts::te_gemm_ts"):
                try:
                    work = (transformer_engine_work(parsed["inputs"], parsed["outputs"])
                            if node.name == "tex_ts::te_gemm_ts" else
                            matrix_work(node.name, parsed["inputs"], parsed["outputs"]))
                except ValueError as error:
                    counts["unsupported_matrix_primitives"] += 1
                    key = "matrix_rejection: " + str(error)
                    if key not in examples:
                        examples[key] = dict(id=node.id, byte_offset=offset)
                else:
                    work.update(node_id=node.id, byte_offset=offset,
                        source_data_deps=list(node.data_deps), source_ctrl_deps=list(node.ctrl_deps))
                    work_records.append(work)
                    counts["normalized_matrix_primitives"] += 1
                    counts[f"normalized_matrix_operator:{node.name}"] += 1
                    counts["normalized_matrix_mac"] += work["work_amount"]
                    counts["normalized_extra_scalar_adds"] += work.get("extra_scalar_adds", 0)
            # Compact source examples only; no synthesized producer, version or lifetime.
            key = f"{kind}:{domain}"
            if key not in examples:
                examples[key] = dict(id=node.id, byte_offset=offset, name=node.name,
                    data_deps=list(node.data_deps), ctrl_deps=list(node.ctrl_deps),
                    attributes=attributes,
                    inputs={k: getattr(node.inputs, k) for k in ("values", "shapes", "types")},
                    outputs={k: getattr(node.outputs, k) for k in ("values", "shapes", "types")})
        final_offset = stream.tell()
    if not dependencies:
        raise ValueError("Empty Chakra rank is not a complete training input")
    combined = {i: dependencies[i] | controls[i] for i in dependencies}
    report = dict(metadata_version=metadata.version, metadata_attributes=attribute_values(metadata),
        nodes=len(dependencies), bytes_read=final_offset,
        counts=dict(sorted(counts.items())), attributes=dict(sorted(attrs_count.items())),
        collective_attribute_counts=dict(sorted(collective.items())),
        data_dependency_graph=graph_summary(dependencies),
        control_reference_graph=graph_summary(controls),
        combined_reference_graph=graph_summary(combined),
        nonzero_start_time_range_micros=[min_start, max_end], examples=examples,
        source_duration_is_target_work=False, tensor_versions_inferred=False)
    return report, signatures, work_records
