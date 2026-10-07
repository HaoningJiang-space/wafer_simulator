"""Explicit upstream integration suite; requires the isolated patched checkout."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

from chakra.schema.protobuf.et_def_pb2 import Node
from chakra.src.converter.pytorch_converter import PyTorchConverter
from chakra.src.converter.pytorch_node import PyTorchNode
from wafer_sim.workloads.chakra import attribute_values, decode_io
from wafer_sim.workloads.chakra_layout import decode_layout
from test_chakra_layout import fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("chakra.src.converter.unpatched_converter",
    ROOT / "third_party/chakra/src/converter/pytorch_converter.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


def source_node(layout=True):
    io, attrs = fixture()
    inputs = dict(zip(("values", "shapes", "types"), copy.deepcopy(io)))
    outputs = dict(values=[], shapes=[], types=[])
    if layout:
        inputs["strides"] = json.loads(attrs["wafer.inputs.strides.v1"])
        outputs["strides"] = []
    attributes = [dict(name=k, value=v) for k, v in dict(
        rf_id=1, fw_parent=0, seq_id=-1, scope=0, tid=1, fw_tid=0, op_schema="").items()]
    return PyTorchNode("1.0.3-chakra.0.0.4", dict(id=1, name="example", ctrl_deps=0,
        exclusive_dur=12, inputs=inputs, outputs=outputs, attrs=attributes))


class ConverterPatchTests(unittest.TestCase):
    def test_original_io_control_attributes_and_time_unchanged(self):
        source = source_node()
        patched = PyTorchConverter().convert_json_to_protobuf_node({1:source}, {}, source)
        original = reference.PyTorchConverter().convert_json_to_protobuf_node({1:source}, {}, source)
        legacy = copy.deepcopy(patched)
        retained = [a for a in legacy.attr if not a.name.startswith("wafer.")]
        del legacy.attr[:]; legacy.attr.extend(retained)
        self.assertEqual(legacy.SerializeToString(), original.SerializeToString())
        self.assertEqual(set(attribute_values(patched)) - set(attribute_values(original)),
                         {"wafer.inputs.strides.v1", "wafer.outputs.strides.v1"})

    def test_protobuf_roundtrip_yields_exact_noncontiguous_footprint(self):
        source = source_node()
        node = PyTorchConverter().convert_json_to_protobuf_node({1:source}, {}, source)
        saved = Node.FromString(node.SerializeToString())
        layout = decode_layout(decode_io(saved.inputs), attribute_values(saved), "inputs")
        self.assertEqual(layout["i:0.0"]["spans"], ((8, 20), (28, 40)))

    def test_legacy_missing_strides_stays_byte_identical(self):
        source = source_node(False)
        actual = PyTorchConverter().convert_json_to_protobuf_node({1:source}, {}, source)
        expected = reference.PyTorchConverter().convert_json_to_protobuf_node({1:source}, {}, source)
        self.assertEqual(actual.SerializeToString(), expected.SerializeToString())
        self.assertEqual(decode_layout(decode_io(actual.inputs), attribute_values(actual), "inputs"), {})

    def test_present_invalid_layout_is_preserved_then_rejected(self):
        source = source_node()
        source.inputs["strides"] = []
        node = PyTorchConverter().convert_json_to_protobuf_node({1:source}, {}, source)
        with self.assertRaisesRegex(ValueError, "argument count"):
            decode_layout(decode_io(node.inputs), attribute_values(node), "inputs")
