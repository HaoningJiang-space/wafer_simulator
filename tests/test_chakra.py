"""File completeness and source-graph semantics, not performance experiments."""
import io
from types import SimpleNamespace
import unittest

from wafer_sim.workloads.chakra import read_frame
from wafer_sim.analysis.chakra_source import decode_io, graph_summary
from wafer_sim.workloads.chakra_work import matrix_work, tensor_reference


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

    def test_matrix_work_uses_shapes_not_source_duration(self):
        inputs = ([[1, 4, 0, 6, 2, "cuda:0"], [2, 5, 0, 12, 2, "cuda:0"]],
                  [[2, 3], [3, 4]], ["Tensor(bfloat16)"] * 2)
        outputs = ([[3, 6, 0, 8, 2, "cuda:0"]], [[2, 4]], ["Tensor(bfloat16)"])
        work = matrix_work("aten::mm", inputs, outputs)
        self.assertEqual((work["work_unit"], work["work_amount"]), ("mac", 24))
        self.assertEqual((work["input_logical_bytes"], work["output_logical_bytes"]), (36, 16))
        self.assertFalse(work["source_time_used"])
        self.assertFalse(work["tensor_versions_resolved"])

    def test_batched_matrix_work_and_invalid_dimensions(self):
        inputs = ([[1, 4, 0, 30, 4, "cuda:0"], [2, 5, 0, 60, 4, "cuda:0"]],
                  [[5, 2, 3], [5, 3, 4]], ["Tensor(float)"] * 2)
        outputs = ([[3, 6, 0, 40, 4, "cuda:0"]], [[5, 2, 4]], ["Tensor(float)"])
        self.assertEqual(matrix_work("aten::bmm", inputs, outputs)["work_amount"], 120)
        inputs[1][1] = [5, 4, 3]
        with self.assertRaisesRegex(ValueError, "dimensions"):
            matrix_work("aten::bmm", inputs, outputs)

    def test_tensor_reference_does_not_infer_lifetime_or_byte_offset(self):
        ref = tensor_reference([11, 7, 12, 6, 4, "cuda:0"], [2, 3], "Tensor(float)")
        self.assertEqual((ref.storage_id, ref.source_offset, ref.logical_bytes), (7, 12, 24))
        with self.assertRaisesRegex(ValueError, "element count"):
            tensor_reference([11, 7, 12, 7, 4, "cuda:0"], [2, 3], "Tensor(float)")
        self.assertIsNone(matrix_work("unrecognized_kernel", None, None))


if __name__ == "__main__":
    unittest.main()
