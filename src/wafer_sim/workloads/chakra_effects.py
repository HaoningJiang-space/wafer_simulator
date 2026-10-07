"""Source operator effects with explicit alias/allocation/write distinctions.

Effects describe a call's IO, not an independently schedulable operation. A
parent and its implementation children must not both be charged. Unsupported
calls retain identities and reasons; schemas alone do not establish semantics
for custom kernels or an initialized, architecture-independent dataflow.
"""
from dataclasses import asdict
import re

from wafer_sim.workloads.chakra_work import tensor_reference, transformer_engine_work


def split_fields(text):
    fields, stack, start = [], [], 0
    pairs = {")": "(", "]": "[", "}": "{"}
    for pos, char in enumerate(text):
        if char in "([{":
            stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]:
                raise ValueError("Unbalanced type/schema fields")
        elif char == "," and not stack:
            fields.append(text[start:pos].strip()); start = pos + 1
    if stack:
        raise ValueError("Unbalanced type/schema fields")
    if text[start:].strip():
        fields.append(text[start:].strip())
    return fields


def tensor_leaves(io, side):
    result = []
    def visit(value, shape, kind, path):
        if kind.startswith("Tensor("):
            ref = tensor_reference(value, shape, kind)
            result.append(dict(path=path, **asdict(ref)))
        elif kind.startswith(("GenericList[", "Tuple[")):
            fields = split_fields(kind[kind.index("[") + 1:-1])
            if (not kind.endswith("]") or not isinstance(value, list) or not isinstance(shape, list)
                    or len(value) != len(shape) or len(fields) != len(value)):
                raise ValueError("Nested tensor IO arity differs")
            for index, (v, s, t) in enumerate(zip(value, shape, fields)):
                visit(v, s, t, path + f".{index}")
        elif "Tensor" in kind:
            raise ValueError("Unsupported tensor container")
    if io is None or len({len(part) for part in io}) != 1:
        raise ValueError("Complete aligned IO required")
    for index, (v, s, t) in enumerate(zip(*io)):
        if not isinstance(t, str):
            raise ValueError("Invalid tensor type")
        visit(v, s, t, f"{side}:{index}")
    return result


def schema_writes(schema, input_count):
    """Limited declared-write extraction, not a general FunctionSchema parser."""
    if not schema or "(" not in schema or ") -> " not in schema:
        raise ValueError("Missing operator schema")
    args = schema[schema.index("(") + 1:schema.rindex(") -> ")]
    fields = [field for field in split_fields(args) if field != "*"]
    if len(fields) != input_count:
        raise ValueError("Operator schema and recorded argument count differ")
    indices = []
    for i, field in enumerate(fields):
        if re.match(r"Tensor\([^)]*!", field):
            indices.append(i)
    return tuple(indices)


def effects(name, schema, inputs, outputs):
    ins, outs = tensor_leaves(inputs, "i"), tensor_leaves(outputs, "o")
    result = dict(category="unresolved", rule=None, reason=None, inputs=ins, outputs=outs,
                  reads=[], writes=[], allocations=[], aliases=[], metadata_inputs=[],
                  source_durations_used=False, source_order_is_target_order=False,
                  allocation_epochs_resolved=False, exact_footprints_resolved=False)
    ip, op = [t["path"] for t in ins], [t["path"] for t in outs]
    def same_storage(a, b):
        return (a["storage_id"], a["source_device"]) == (b["storage_id"], b["source_device"])
    def finish(category, rule, **fields):
        result.update(category=category, rule=rule, **fields)
        return result
    if name == "tex_ts::te_gemm_ts":
        work = transformer_engine_work(inputs, outputs)
        reads = ["i:0", "i:5"] + (["i:10"] if work["reads_old_destination"] else [])
        return finish("write", "dense_TE_v1.13_22_argument_ABI", reads=reads, writes=["o:0"],
                      # The pointer is already allocated; output is not a new allocation.
                      destination_input="i:10", source_workspace_input="i:18")
    if name in {"aten::set_", "aten::resize_", "aten::resize_as_"}:
        return finish("storage_rebind", "explicit_storage_metadata_operation", metadata_inputs=ip,
                      reason="Storage extent/generation and possibly copied data require explicit lowering")
    if name in {"aten::empty", "aten::empty_strided", "aten::empty_like", "aten::new_empty",
                "aten::new_empty_strided"}:
        return finish("allocate_uninitialized", "aten_empty_family", allocations=op, metadata_inputs=ip)
    aliases = {"aten::view", "aten::_unsafe_view", "aten::view_as", "aten::_reshape_alias",
               "aten::as_strided", "aten::transpose", "aten::t", "aten::permute", "aten::slice",
               "aten::select", "aten::narrow", "aten::detach", "detach", "aten::detach_", "detach_",
               "aten::squeeze", "aten::unsqueeze", "aten::expand", "aten::expand_as",
               "aten::split", "aten::split_with_sizes", "aten::unbind"}
    # reshape/contiguous/to can either alias or copy. Only an observed alias
    # branch is metadata; a new-storage branch still needs its child work.
    conditional_alias = name in {"aten::reshape", "aten::contiguous", "aten::to"}
    if name in aliases or conditional_alias:
        links = []
        for out in outs:
            matches = [t["path"] for t in ins if same_storage(t, out)]
            if not matches:
                result["reason"] = "Alias/copy branch has no matching input storage"
                return result
            links.append(dict(output=out["path"], inputs=matches))
        if not links:
            result["reason"] = "Alias operation has no tensor output"
            return result
        return finish("alias", "observed_same_storage_view", aliases=links, metadata_inputs=ip)
    if name in {"aten::copy_", "aten::fill_", "aten::zero_", "aten::add_", "aten::mul_", "aten::div_"}:
        if not ins or not outs or ins[0]["path"] != "i:0" or len(outs) != 1 or not same_storage(ins[0], outs[0]):
            raise ValueError("In-place destination does not match input storage")
        declared = schema_writes(schema, len(inputs[0]))
        if 0 not in declared:
            raise ValueError("In-place rule and schema disagree")
        reads = ip[1:] if name in {"aten::copy_", "aten::fill_", "aten::zero_"} else ip
        return finish("write", "aten_explicit_destination", reads=reads, writes=op, destination_input="i:0")
    if name.startswith("aten::") and schema:
        try:
            declared = schema_writes(schema, len(inputs[0]))
        except ValueError as error:
            result["reason"] = str(error)
            return result
        if declared:
            # e.g. index_put_ writes only a subset; ! does not justify a full overwrite.
            return finish("declared_mutation", "schema_write_annotation", operand_inputs=ip,
                          potential_writes=[p for p in ip if int(p[2:].split(".")[0]) in declared],
                          reason="Write extent and overwrite/read-modify-write semantics unresolved")
        # Tensor aliases in schema must be interpreted even without a write flag.
        if re.search(r"Tensor\([^)]*\)", schema):
            result["reason"] = "Unmodeled schema alias semantics"
            return result
        if outs and any(same_storage(a, b) for a in ins for b in outs):
            result["reason"] = "Unannotated input/output storage alias"
            return result
        # A tensor argument may be used only for shape/device metadata. A
        # functional schema does not prove a byte read or initialized output.
        return finish("schema_functional", "aten_schema_no_alias_no_mutation",
                      operand_inputs=ip, result_outputs=op,
                      reason="Requires operator-specific work/access semantics")
    result["reason"] = "No supported operator effect rule"
    return result
