"""Supported logical primitives from Chakra IO, without source timing.

This is a partial normalization surface, not a complete training importer.
Tensor/storage references retain source identity; they are not immutable
versions and cannot yet be passed as spatial.DataObject IDs.
"""
from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class TensorReference:
    tensor_id: int
    storage_id: int
    source_offset: int  # retain source convention; not a derived byte address
    num_elements: int
    element_bytes: int
    source_device: str
    shape: tuple[int, ...]
    dtype: str

    @property
    def logical_bytes(self):
        return self.num_elements * self.element_bytes


def tensor_reference(value, shape, kind):
    if (not isinstance(kind, str) or not kind.startswith("Tensor(") or
            not isinstance(value, list) or len(value) != 6 or
            any(type(x) is not int or x < 0 for x in value[:5]) or
            not isinstance(value[5], str) or not value[5] or value[4] == 0 or
            not isinstance(shape, list) or any(type(x) is not int or x < 0 for x in shape)):
        raise ValueError("Unsupported tensor descriptor")
    if math.prod(shape) != value[3]:
        raise ValueError("Tensor shape and element count disagree")
    return TensorReference(*value, tuple(shape), kind)


def matrix_work(name, inputs, outputs):
    """Exact dense MAC count for mm/bmm; no kernel or parent-op double count.

    Call only for CPU dispatcher primitives, not their attached GPU kernels.
    One MAC denotes one multiply-accumulate in the conventional dense work
    count; it is not a measured instruction or a calibrated target duration.
    """
    if name not in ("aten::mm", "aten::bmm"):
        return None
    if inputs is None or outputs is None or len(inputs[0]) != 2 or len(outputs[0]) != 1:
        raise ValueError("Matrix primitive requires two tensors and one output")
    lhs, rhs = [tensor_reference(*args) for args in zip(*inputs)]
    out = tensor_reference(*(part[0] for part in outputs))
    ndim = 2 if name == "aten::mm" else 3
    if any(len(t.shape) != ndim for t in (lhs, rhs, out)):
        raise ValueError("Unexpected matrix primitive rank")
    m, k = lhs.shape[-2:]
    other_k, n = rhs.shape[-2:]
    batch = 1 if ndim == 2 else lhs.shape[0]
    expected_output = (m, n) if ndim == 2 else (batch, m, n)
    if k != other_k or out.shape != expected_output or (ndim == 3 and rhs.shape[0] != batch):
        raise ValueError("Matrix dimensions disagree")
    if len({t.dtype for t in (lhs, rhs, out)}) != 1:
        raise ValueError("Mixed-type matrix primitive requires an explicit model")
    return dict(operator=name, work_unit="mac", work_amount=batch * m * n * k,
        inputs=[asdict(lhs), asdict(rhs)], outputs=[asdict(out)],
        input_logical_bytes=lhs.logical_bytes + rhs.logical_bytes,
        output_logical_bytes=out.logical_bytes,
        source_time_used=False, tensor_versions_resolved=False)
