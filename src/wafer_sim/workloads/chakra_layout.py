"""Explicit optional source strides -> exact accesses; never infer contiguity."""
import json

from wafer_sim.workloads.chakra_effects import tensor_leaves
from wafer_sim.workloads.tensor_effect_binding import AccessBinding
from wafer_sim.workloads.tensor_versions import strided_footprint


def decode_layout(io, attrs, side):
    if side not in {"inputs", "outputs"}:
        raise ValueError("Expected inputs or outputs layout")
    name = f"wafer.{side}.strides.v1"
    if name not in attrs:
        return {}  # Legacy capture: no layout evidence, not contiguous.
    if not isinstance(attrs[name], str):
        raise ValueError("Stride attribute must contain JSON text")
    nested = json.loads(attrs[name])
    if not isinstance(nested, list) or len(nested) != len(io[0]):
        raise ValueError("Stride argument count differs from IO")
    result = {}
    for ref in tensor_leaves(io, "i" if side == "inputs" else "o"):
        stride = nested
        try:
            for index in ref["path"][2:].split("."):
                if not isinstance(stride, list):
                    raise ValueError("Stride nesting differs from tensor IO")
                stride = stride[int(index)]
        except IndexError as error:
            raise ValueError("Missing nested tensor strides") from error
        if (not isinstance(stride, list) or len(stride) != len(ref["shape"]) or
                any(type(v) is not int or v < 0 for v in stride)):
            raise ValueError("Explicit nonnegative stride per tensor dimension required")
        result[ref["path"]] = dict(strides=stride,
            spans=strided_footprint(ref["shape"], stride, ref["element_bytes"], ref["source_offset"]),
            source_attribute=name)
    return result


def access_from_layout(state, rank, ref, layout, storage):
    """Bind a layout to a caller-proved live generation, without initializing it."""
    if (storage.rank, storage.device, storage.source_id) != (rank, ref["source_device"], ref["storage_id"]):
        raise ValueError("Layout bound to another source storage")
    spans = strided_footprint(ref["shape"], layout["strides"], ref["element_bytes"], ref["source_offset"])
    if tuple(map(tuple, layout["spans"])) != spans:
        raise ValueError("Saved footprint differs from source strides")
    return AccessBinding(storage, state.check_access(storage, spans))
