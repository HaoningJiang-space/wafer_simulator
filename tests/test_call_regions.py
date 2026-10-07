"""Analytical source-ownership tests, not simulator smoke workloads."""
import unittest
import gzip
import json
from pathlib import Path
import tempfile

from wafer_sim.workloads.call_regions import Call, partition_calls, quotient
from wafer_sim.workloads.chakra_regions import write_partition
from wafer_sim.analysis.call_regions import validate_partition


def call(node, parent=0, deps=(), category="unresolved", name="scope", domain="CPU",
         storage=1, output="tensor", meta=False, matrix=False):
    return Call(node, parent, tuple(deps), name, domain, category,
                frozenset({(storage, "cuda:0")}), (output,) if output else (), meta, matrix)


class CallRegionTests(unittest.TestCase):
    def partition(self, *calls):
        return partition_calls({c.node_id: c for c in calls})

    def test_alias_chain_owned_once(self):
        result = self.partition(call(1, category="alias"), call(2, 1, (1,), "alias"),
                                call(3, 2, (2,), "alias"), call(4, deps=(2, 3)))
        self.assertEqual(result.owners, {1: 1, 2: 1, 3: 1, 4: 4})
        self.assertEqual(result.rules[1], "alias_metadata")

    def test_unknown_child_keeps_parent_residual(self):
        result = self.partition(call(1, category="alias"), call(2, 1, (1,)),
                                call(3, 1, (2,), "alias"), call(4, 3, (3,), "alias"))
        self.assertIsNone(result.rules[1])
        self.assertEqual(result.owners, {1: 1, 2: 2, 3: 3, 4: 3})

    def test_alias_different_storage_not_absorbed(self):
        result = self.partition(call(1, category="alias"), call(2, 1, (1,), "alias", storage=2))
        self.assertEqual(result.owners, {1: 1, 2: 2})

    def test_allocation_requires_exact_output(self):
        for output, expected in (("tensor", 1), ("another_view", 2)):
            result = self.partition(call(1, category="allocate_uninitialized"),
                                    call(2, 1, (1,), "allocate_uninitialized", output=output))
            self.assertEqual(result.owners[2], expected)

    def test_repeated_allocation_siblings_not_merged(self):
        result = self.partition(call(1, category="allocate_uninitialized"),
                                call(2, 1, (1,), "allocate_uninitialized"),
                                call(3, 1, (2,), "allocate_uninitialized"))
        self.assertEqual(result.owners, {1: 1, 2: 2, 3: 3})

    def test_matrix_owns_gpu_implementation(self):
        result = self.partition(call(1, name="aten::mm", category="schema_functional", matrix=True),
                                call(2, 1, (1,), "device_implementation", "gemm", "GPU"))
        self.assertEqual(result.owners, {1: 1, 2: 1})
        self.assertEqual(result.rules[1], "matrix_with_device_implementation")

    def test_unverified_matrix_and_meta_not_compute(self):
        for matrix, meta in ((False, False), (True, True)):
            result = self.partition(call(1, name="aten::mm", matrix=matrix, meta=meta),
                                    call(2, 1, (1,), "device_implementation", "gemm", "GPU"))
            self.assertIsNone(result.rules[1])
            self.assertEqual(result.owners[2], 2)

    def test_gpu_collective_not_gemm_child(self):
        result = self.partition(call(1, name="aten::mm", matrix=True),
                                call(2, 1, (1,), "device_implementation", "ncclKernel", "GPU"))
        self.assertIsNone(result.rules[1])

    def test_explicit_write_but_not_unknown_cpu_child(self):
        result = self.partition(call(1, category="write", name="aten::zero_"),
                                call(2, 1, (1,), "device_implementation", "memset", "GPU"))
        self.assertEqual(result.owners[2], 1)
        result = self.partition(call(1, category="write", name="aten::zero_"), call(2, 1, (1,)))
        self.assertIsNone(result.rules[1])

    def test_interleaving_refines_cyclic_region_only(self):
        # Source 1 -> 3 -> 2 is acyclic, but merging parent 1 with child 2 is not.
        calls = [call(1, category="alias"), call(2, 1, (3,), "alias"), call(3, deps=(1,)),
                 call(4, deps=(2,), category="alias"), call(5, 4, (4,), "alias")]
        result = self.partition(*calls)
        self.assertEqual(result.owners, {1: 1, 2: 2, 3: 3, 4: 4, 5: 4})
        self.assertEqual(result.rejected, {1: "source_dependency_interleaves_region"})
        self.assertIsNone(result.rules[1])
        self.assertEqual(result.rules[4], "alias_metadata")

    def test_duplicate_edges_preserved_on_source(self):
        calls = {1: call(1), 2: call(2, deps=(1, 1))}
        result = partition_calls(calls)
        self.assertEqual(calls[2].dependencies, (1, 1))
        self.assertEqual(quotient(calls, result.owners)[2], {1})

    def test_missing_parent_or_dependency_rejected(self):
        for calls in ((call(1, 9),), (call(1, deps=(9,)),)):
            with self.assertRaises(ValueError):
                self.partition(*calls)

    def test_parent_and_dependency_cycles_rejected(self):
        for calls in ((call(1, 2), call(2, 1)), (call(1, deps=(2,)), call(2, deps=(1,)))):
            with self.assertRaises(ValueError):
                self.partition(*calls)

    def test_external_root_is_not_data_ready(self):
        with self.assertRaises(ValueError):
            self.partition(call(1, deps=(0,)))
        with self.assertRaises(ValueError):
            self.partition(call(0))


class RegionReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.jsonl.gz"
        ref = dict(tensor_id=1, storage_id=2, source_offset=0, num_elements=4, element_bytes=4,
                   source_device="cuda:0", shape=[4], dtype="Tensor(float)", path="o:0")
        rows = [dict(rank=0, node_id=n, byte_offset=n*10, name="aten::view", source_domain="CPU",
                     source_ctrl_deps=[parent], source_data_deps=deps,
                     effects=dict(category="alias", inputs=[ref], outputs=[ref]))
                for n, parent, deps in ((1, 0, []), (2, 1, [1, 1]), (3, 0, [2]))]
        self.save(self.source, rows)
        write_partition(self.source, self.root, 0, {})

    @staticmethod
    def save(path, rows):
        with gzip.open(path, "wt") as stream:
            for row in rows:
                stream.write(json.dumps(row) + "\n")

    @staticmethod
    def read(path):
        with gzip.open(path, "rt") as stream:
            return [json.loads(line) for line in stream]

    def validate(self):
        return validate_partition(self.source, self.root / "rank-00-owners.jsonl.gz",
                                  self.root / "rank-00-regions.jsonl.gz", self.root / "rank-00-edges.jsonl.gz", 0, {})

    def test_independent_round_trip(self):
        checked = self.validate()
        self.assertEqual(checked["counts"]["nodes"], 3)
        self.assertEqual(checked["counts"]["data_dependencies"], 3)
        self.assertEqual(checked["counts"]["absorbed_records"], 1)

    def test_deleted_duplicate_dependency_detected(self):
        path = self.root / "rank-00-edges.jsonl.gz"
        rows = self.read(path)
        rows.pop(3)
        self.save(path, rows)
        with self.assertRaises(ValueError):
            self.validate()

    def test_target_completeness_claim_detected(self):
        path = self.root / "rank-00-regions.jsonl.gz"
        rows = self.read(path)
        rows[0]["complete_target_operation"] = True
        self.save(path, rows)
        with self.assertRaises(ValueError):
            self.validate()

    def test_unknown_source_child_cannot_be_absorbed(self):
        rows = self.read(self.source)
        rows[1]["effects"]["category"] = "unresolved"
        self.save(self.source, rows)
        with self.assertRaises(ValueError):
            self.validate()

    def test_missing_source_row_detected(self):
        path = self.root / "rank-00-owners.jsonl.gz"
        self.save(path, self.read(path)[:-1])
        with self.assertRaises(ValueError):
            self.validate()


if __name__ == "__main__":
    unittest.main()
