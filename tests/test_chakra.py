"""File completeness and source-graph semantics, not performance experiments."""
import io
from types import SimpleNamespace
import unittest

from wafer_sim.workloads.chakra import read_frame
from wafer_sim.analysis.chakra_source import decode_io, graph_summary


class Payload:
    def ParseFromString(self, payload):
        self.payload = payload


class ChakraSourceTests(unittest.TestCase):
    def test_clean_eof_is_distinct_from_empty_message(self):
        self.assertIsNone(read_frame(io.BytesIO(), Payload))
        self.assertEqual(read_frame(io.BytesIO(b"\x00"), Payload)[1].payload, b"")

    def test_truncated_prefix_fails(self):
        for payload in (b"\x80", b"\x80\x80\x80\x80"):
            with self.assertRaisesRegex(ValueError, "Truncated"):
                read_frame(io.BytesIO(payload), Payload)

    def test_truncated_payload_fails_even_at_protobuf_field_boundary(self):
        with self.assertRaisesRegex(ValueError, "Truncated"):
            read_frame(io.BytesIO(b"\x03ab"), Payload)

    def test_uint32_length_and_allocation_limit(self):
        for payload in (b"\xff\xff\xff\xff\x10", b"\xff" * 5):
            with self.assertRaisesRegex(ValueError, "uint32"):
                read_frame(io.BytesIO(payload), Payload)
        with self.assertRaisesRegex(ValueError, "limit"):
            read_frame(io.BytesIO(b"\x05abcde"), Payload, max_bytes=4)

    def test_consecutive_messages_keep_offsets(self):
        stream = io.BytesIO(b"\x01a\x02bc")
        self.assertEqual(read_frame(stream, Payload)[0], 0)
        offset, message = read_frame(stream, Payload)
        self.assertEqual((offset, message.payload), (2, b"bc"))
        self.assertIsNone(read_frame(stream, Payload))

    def test_io_literals_retain_shapes_identity_and_device(self):
        info = SimpleNamespace(values="[[1, 2, 0, 6, 4, 'cuda:0']]", shapes="[[2, 3]]", types="['Tensor(float)']")
        values, shapes, types = decode_io(info)
        self.assertEqual(values[0], [1, 2, 0, 6, 4, "cuda:0"])
        self.assertEqual(shapes, [[2, 3]])
        self.assertEqual(types, ["Tensor(float)"])

    def test_io_rejects_code_and_misalignment(self):
        for text in ("[f()]", "{}", "[1, 2]"):
            with self.assertRaises((ValueError, SyntaxError)):
                decode_io(SimpleNamespace(values=text, shapes="[[]]", types="['Int']"))

    def test_missing_control_root_not_silently_removed(self):
        report = graph_summary({1: {0}, 2: {1}})
        self.assertEqual(report["missing_examples"], [0])
        self.assertFalse(report["closed_acyclic"])

    def test_cycle_and_valid_data_graph(self):
        self.assertFalse(graph_summary({1: {2}, 2: {1}})["closed_acyclic"])
        self.assertTrue(graph_summary({1: set(), 2: {1}})["closed_acyclic"])


if __name__ == "__main__":
    unittest.main()
