"""Complete source-effect ledger and coverage; no target workload filtering."""
from collections import Counter
import gzip
import json

from wafer_sim.workloads.chakra import read_metadata, nodes, decode_io, attribute_values
from wafer_sim.workloads.chakra_effects import effects


def inspect_effects(path, schema, output, rank):
    counts, operators = Counter(), Counter()
    first_location, changed_ids, examples = {}, set(), {}
    with path.open("rb") as stream, gzip.open(output, "wt", compresslevel=1) as ledger:
        read_metadata(stream, schema)
        for offset, node in nodes(stream, schema):
            attrs = attribute_values(node)
            cpu = attrs.get("is_cpu_op")
            if type(cpu) is not bool:
                raise ValueError("Source domain missing")
            row = dict(rank=rank, node_id=node.id, byte_offset=offset, name=node.name,
                       source_ctrl_deps=list(node.ctrl_deps), source_data_deps=list(node.data_deps),
                       source_domain="CPU" if cpu else "GPU", source_op_schema=attrs.get("op_schema", ""))
            counts["nodes"] += 1
            if not cpu:
                row["effects"] = dict(category="device_implementation", reason="Not a second logical operator")
            elif node.type == schema.METADATA_NODE:
                row["effects"] = dict(category="source_metadata", reason="Not target compute")
            else:
                try:
                    row["effects"] = effects(node.name, row["source_op_schema"],
                                             decode_io(node.inputs), decode_io(node.outputs))
                except (ValueError, SyntaxError, TypeError, RecursionError) as error:
                    row["effects"] = dict(category="unsupported_descriptor_or_rule", reason=str(error))
                effect = row["effects"]
                refs = effect.get("inputs", []) + effect.get("outputs", [])
                devices = {r["source_device"] for r in refs if r["num_elements"]}
                row["contains_meta_tensors"] = "meta" in devices
                row["only_meta_tensors"] = devices == {"meta"}
                counts["cpu_calls"] += 1
                counts["tensor_occurrences"] += len(refs)
                counts["calls_containing_meta_tensors"] += row["contains_meta_tensors"]
                counts["calls_with_only_meta_tensors"] += row["only_meta_tensors"]
                for ref in refs:
                    identity = ref["tensor_id"]
                    location = ref["storage_id"], ref["source_device"]
                    first = first_location.setdefault(identity, location)
                    if first != location:
                        changed_ids.add(identity)
                        examples.setdefault("tensor_identity_reused", dict(node_id=node.id,
                            byte_offset=offset, tensor_id=identity, first_location=first, observed_location=location))
                    counts["nonzero_tensor_offsets"] += ref["source_offset"] != 0
            category = row["effects"]["category"]
            counts["category:" + category] += 1
            operators[(node.name, category)] += 1
            if category in {"unresolved", "unsupported_descriptor_or_rule", "declared_mutation", "storage_rebind"}:
                examples.setdefault(category, dict(node_id=node.id, name=node.name,
                    byte_offset=offset, reason=row["effects"].get("reason")))
            ledger.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
        size = stream.tell()
    return dict(rank=rank, input_bytes=size, counts=dict(sorted(counts.items())),
                distinct_tensor_ids=len(first_location), tensor_ids_observed_at_multiple_locations=len(changed_ids),
                examples=examples,
                complete_source_read=True, complete_target_workload=False), operators
