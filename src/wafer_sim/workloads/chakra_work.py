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


def transformer_engine_work(inputs, outputs):
    """Dense unfused te_gemm_ts under the recorded 22-argument v1.13 ABI.

    Argument roles, column-major GEMM dimensions and accumulation follow the
    pinned NVIDIA source. Its source GPU workspace is metadata only. Empty
    scale/bias/GELU tensors are required; FP8 and fused epilogues need their
    own logical operators. This does not assert the capture's build version.
    """
    if inputs is None or outputs is None or any(len(x) != 22 for x in inputs) or any(len(x) != 1 for x in outputs):
        raise ValueError("TE GEMM requires its complete 22-argument ABI")
    values, shapes, types = inputs
    def tensor(index):
        return tensor_reference(values[index], shapes[index], types[index])
    for index in (4, 9, 17, 20, 21):
        if type(values[index]) is not int or values[index] not in (0, 1):
            raise ValueError("Unsupported TE boolean flag")
    a, b, dest = tensor(0), tensor(5), tensor(10)
    out = tensor_reference(*(part[0] for part in outputs))
    if dest != out:
        raise ValueError("TE output must preserve the destination tensor reference")
    if any(len(t.shape) != 2 or not t.num_elements for t in (a, b, dest)):
        raise ValueError("TE dense GEMM requires nonempty matrices")
    dtype = {3: ("Tensor(float)", 4), 4: ("Tensor(c10::Half)", 2), 5: ("Tensor(c10::BFloat16)", 2)}
    for index, ref in ((3, a), (8, b), (12, dest)):
        if type(values[index]) is not int or dtype.get(values[index]) != (ref.dtype, ref.element_bytes):
            raise ValueError("Unsupported TE dtype or inconsistent tensor descriptor")
    if a.dtype != b.dtype:
        raise ValueError("Mixed operand types need an explicit TE model")
    for index in (1, 6, 11, 13, 14, 16):
        if tensor(index).num_elements:
            raise ValueError("TE scaling or fused epilogue requires separate work semantics")
    ta, tb = values[4], values[9]
    if ta and tb:
        raise ValueError("Pinned TE implementation rejects TT layout")
    m, k = a.shape if ta else a.shape[::-1]
    n, other_k = b.shape[::-1] if tb else b.shape
    if k != other_k or dest.shape != (n, m):
        raise ValueError("TE matrix dimensions disagree")
    workspace = tensor(18)
    if type(values[19]) is not int or not 0 <= values[19] <= workspace.logical_bytes:
        raise ValueError("Invalid source TE workspace size")
    accumulating = bool(values[20])
    operands = [a, b] + ([dest] if accumulating else [])
    return dict(operator="tex_ts::te_gemm_ts", work_unit="mac", work_amount=m * n * k,
        extra_scalar_adds=m * n if accumulating else 0,
        inputs=[asdict(t) for t in operands], outputs=[asdict(out)],
        input_logical_bytes=sum(t.logical_bytes for t in operands), output_logical_bytes=out.logical_bytes,
        transpose_a=bool(ta), transpose_b=bool(tb), reads_old_destination=accumulating,
        source_workspace_bytes=values[19], source_workspace_is_target_scratch=False,
        semantic_reference="NVIDIA/TransformerEngine@e5edd6cc3d5a868bb3fe4e81088d22aab505a30d",
        source_time_used=False, tensor_versions_resolved=False)
