"""Exact source-layout semantics and allocation binding."""
import copy
import json
import unittest

from wafer_sim.workloads.chakra_effects import tensor_leaves
from wafer_sim.workloads.chakra_layout import decode_layout, access_from_layout
from wafer_sim.workloads.tensor_versions import ByteVersions


def fixture():
    io = ([[[1, 101, 2, 6, 4, "cuda:0"]]], [[[2, 3]]], ["GenericList[Tensor(float)]"])
    attrs = {"wafer.inputs.strides.v1": json.dumps([[[5, 1]]])}
    return io, attrs


class LayoutTests(unittest.TestCase):
    def test_nested_strided_tensor_retains_holes_and_element_offset(self):
        io, attrs = fixture()
        layout = decode_layout(io, attrs, "inputs")["i:0.0"]
        self.assertEqual(layout["spans"], ((8, 20), (28, 40)))
        state = ByteVersions()
        storage = state.allocate(0, "cuda:0", 101, 40)
        ref = tensor_leaves(io, "i")[0]
        binding = access_from_layout(state, 0, ref, layout, storage)
        self.assertEqual(binding.spans, layout["spans"])
        with self.assertRaisesRegex(ValueError, "uninitialized"):
            state.read(storage, binding.spans)

    def test_scalar_and_zero_stride_broadcast_are_not_contiguous_defaults(self):
        io = ([[1, 101, 0, 1, 4, "cuda:0"]], [[]], ["Tensor(float)"])
        attrs = {"wafer.outputs.strides.v1": "[[]]"}
        self.assertEqual(decode_layout(io, attrs, "outputs")["o:0"]["spans"], ((0, 4),))
        io, attrs = fixture()
        attrs["wafer.inputs.strides.v1"] = "[[[0,1]]]"
        self.assertEqual(decode_layout(io, attrs, "inputs")["i:0.0"]["spans"], ((8, 20),))

    def test_absent_metadata_remains_unknown(self):
        io, _ = fixture()
        self.assertEqual(decode_layout(io, {}, "inputs"), {})

    def test_malformed_or_partial_layout_rejected(self):
        io, _ = fixture()
        for value in ("[]", "{}", "[[[]]]", "[[[1]]]", "[[[-1,1]]]", "[[[true,1]]]", "[f()]", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                decode_layout(io, {"wafer.inputs.strides.v1": value}, "inputs")

    def test_stale_or_different_allocation_and_tampered_footprint_rejected(self):
        io, attrs = fixture()
        layout = decode_layout(io, attrs, "inputs")["i:0.0"]
        ref = tensor_leaves(io, "i")[0]
        state = ByteVersions()
        first = state.allocate(0, "cuda:0", 101, 40)
        state.allocate(0, "cuda:0", 101, 40)
        with self.assertRaisesRegex(ValueError, "stale"):
            access_from_layout(state, 0, ref, layout, first)
        wrong = state.allocate(1, "cuda:0", 101, 40)
        with self.assertRaisesRegex(ValueError, "another"):
            access_from_layout(state, 0, ref, layout, wrong)
        small = state.allocate(0, "cuda:0", 101, 39)
        with self.assertRaisesRegex(ValueError, "capacity"):
            access_from_layout(state, 0, ref, layout, small)
        layout = copy.deepcopy(layout); layout["spans"] = ((8, 32),)
        with self.assertRaisesRegex(ValueError, "footprint"):
            access_from_layout(state, 0, ref, layout, small)
