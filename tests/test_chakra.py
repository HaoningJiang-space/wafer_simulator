"""File completeness and source-graph semantics, not performance experiments."""
import io
from types import SimpleNamespace
import unittest

from wafer_sim.workloads.chakra import read_frame
from wafer_sim.analysis.chakra_source import decode_io, graph_summary
from wafer_sim.workloads.chakra_work import matrix_work, tensor_reference, transformer_engine_work


def te_fixture(transa=1, transb=0, accumulate=0):
    """Analytic M=2, N=4, K=3; no captured workload bytes."""
    empty = [99, 98, 0, 0, 4, "cpu"]
    values, shapes, types = [0] * 22, [[] for _ in range(22)], ["Int"] * 22
    for index in (1, 6, 11, 13, 14, 16):
        values[index], shapes[index], types[index] = empty[:], [0], "Tensor(float)"
    for index, dims in ((0, [2, 3] if transa else [3, 2]),
                        (5, [3, 4] if transb else [4, 3]), (10, [4, 2])):
        values[index] = [index + 1, index + 2, 0, dims[0] * dims[1], 2, "cuda:0"]
        shapes[index], types[index] = dims, "Tensor(c10::BFloat16)"
    for index in (3, 8, 12, 15): values[index] = 5
    values[4], values[9], values[20] = transa, transb, accumulate
    values[18], shapes[18], types[18] = [70, 71, 0, 16, 1, "cuda:0"], [16], "Tensor(unsigned char)"
    values[19] = 16
    return (values, shapes, types), ([values[10]], [shapes[10]], [types[10]])


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

    def test_te_non_square_transpose_conventions(self):
        for ta, tb in ((1, 0), (0, 0), (0, 1)):
            work = transformer_engine_work(*te_fixture(ta, tb))
            self.assertEqual(work["work_amount"], 24)
            self.assertEqual(work["output_logical_bytes"], 16)
        with self.assertRaisesRegex(ValueError, "TT"):
            transformer_engine_work(*te_fixture(1, 1))

    def test_te_accumulation_reads_destination_and_source_scratch_stays_separate(self):
        work = transformer_engine_work(*te_fixture(accumulate=1))
        self.assertEqual(len(work["inputs"]), 3)
        self.assertEqual(work["extra_scalar_adds"], 8)
        self.assertEqual(work["input_logical_bytes"], 52)
        self.assertTrue(work["reads_old_destination"])
        self.assertFalse(work["source_workspace_is_target_scratch"])

    def test_te_rejects_fp8_fusion_and_mismatched_output(self):
        for index, replacement in ((3, 6), (4, 3), (19, 17)):
            inputs, outputs = te_fixture()
            inputs[0][index] = replacement
            with self.assertRaises(ValueError): transformer_engine_work(inputs, outputs)
        inputs, outputs = te_fixture()
        inputs[0][14] = [91, 92, 0, 2, 4, "cpu"]
        inputs[1][14] = [2]
        with self.assertRaisesRegex(ValueError, "epilogue"):
            transformer_engine_work(inputs, outputs)
        inputs, outputs = te_fixture()
        outputs[0][0] = [90, 91, 0, 8, 2, "cuda:0"]
        with self.assertRaisesRegex(ValueError, "destination"):
            transformer_engine_work(inputs, outputs)


if __name__ == "__main__":
    unittest.main()
