"""Analytical data-value tests, with an independent byte-array oracle."""
import random
import unittest

from wafer_sim.workloads.tensor_versions import ByteVersions, strided_footprint
from wafer_sim.workloads.chakra_effects import effects, tensor_leaves
from wafer_sim.workloads.tensor_effect_binding import AccessBinding, apply_effect
from test_chakra import te_fixture


def tensor(tid, sid, elements=8, offset=0, shape=None):
    return [tid, sid, offset, elements, 4, "cuda:0"], shape or [elements], "Tensor(float)"


def io(*tensors):
    return tuple(list(items) for items in zip(*tensors)) if tensors else ([], [], [])


class TensorVersionsTests(unittest.TestCase):
    def test_transpose_has_same_bytes_without_materialization(self):
        self.assertEqual(strided_footprint((2, 3), (3, 1), 4), ((0, 24),))
        self.assertEqual(strided_footprint((3, 2), (1, 3), 4), ((0, 24),))

    def test_slice_broadcast_and_scalar_footprints(self):
        self.assertEqual(strided_footprint((3,), (2,), 2, 1), ((2, 4), (6, 8), (10, 12)))
        self.assertEqual(strided_footprint((6, 4), (0, 1), 4), ((0, 16),))
        self.assertEqual(strided_footprint((), (), 8, 2), ((16, 24),))
        self.assertEqual(strided_footprint((0, 4), (4, 1), 4), ())

    def test_missing_strides_and_large_irregular_views_rejected(self):
        with self.assertRaises(ValueError): strided_footprint((2, 3), None, 4)
        with self.assertRaises(ValueError): strided_footprint((2,), (-1,), 4)
        with self.assertRaisesRegex(ValueError, "limit"):
            strided_footprint((100,), (2,), 4, max_spans=4)
        self.assertEqual(strided_footprint((1000000,), (1,), 4, max_spans=4), ((0, 4000000),))

    def test_view_reads_versions_before_and_after_partial_update(self):
        state = ByteVersions()
        key = state.allocate(0, "cuda:0", 9, 24, initial="declared input")
        old = state.read(key, ((0, 24),))
        new = state.write(key, ((8, 16),), "slice_update", "known slice")
        observed = state.read(key, ((0, 24),))
        self.assertEqual([(s.start, s.stop, s.version.producer) for s in observed],
                         [(0, 8, None), (8, 16, "slice_update"), (16, 24, None)])
        self.assertNotEqual(old[0].version, new)
        self.assertEqual(old[0].stop, 24)  # earlier read is an immutable value record

    def test_allocation_is_not_initialized_and_writes_are_atomic(self):
        state = ByteVersions(); key = state.allocate(0, "cuda:0", 1, 16)
        with self.assertRaisesRegex(ValueError, "uninitialized"): state.read(key, ((0, 4),))
        with self.assertRaisesRegex(ValueError, "capacity"):
            state.write(key, ((0, 4), (20, 24)), "bad", "bounds")
        with self.assertRaises(ValueError): state.read(key, ((0, 4),))
        state.write(key, ((0, 4),), "good", "write")
        self.assertEqual(state.read(key, ((0, 4),))[0].version.producer, "good")
        with self.assertRaises(ValueError): state.read(key, ((0, 16),))

    def test_storage_reuse_invalidates_old_alias_and_preserves_rank_identity(self):
        state = ByteVersions()
        old = state.allocate(0, "cuda:0", 1, 8, initial="old input")
        other = state.allocate(1, "cuda:0", 1, 8, initial="other rank")
        new = state.allocate(0, "cuda:0", 1, 8)
        self.assertNotEqual(old, new)
        with self.assertRaisesRegex(ValueError, "stale"): state.read(old, ((0, 8),))
        with self.assertRaises(ValueError): state.read(new, ((0, 8),))
        self.assertEqual(state.read(other, ((0, 8),))[0].version.provenance, "other rank")

    def test_unknown_write_does_not_reuse_previous_producer(self):
        state = ByteVersions(); key = state.allocate(0, "cuda:0", 1, 16, initial="input")
        state.invalidate(key, ((4, 8),))
        with self.assertRaises(ValueError): state.read(key, ((0, 16),))
        self.assertEqual(len(state.read(key, ((8, 16),))), 1)
        state.write(key, ((4, 8),), "repair", "known overwrite")
        self.assertEqual(sum(s.stop - s.start for s in state.read(key, ((0, 16),))), 16)

    def test_random_overwrites_against_independent_byte_array(self):
        rng = random.Random(42)
        state = ByteVersions(); key = state.allocate(0, "cuda:0", 1, 64, initial="input")
        expected = [None] * 64
        for i in range(200):
            a = rng.randrange(64); b = rng.randrange(a + 1, 65)
            producer = f"write{i}"
            state.write(key, ((a, b),), producer, "oracle comparison")
            expected[a:b] = [producer] * (b - a)
            actual = [s.version.producer for s in state.read(key, ((0, 64),))
                      for _ in range(s.start, s.stop)]
            self.assertEqual(actual, expected)

    def test_nested_collective_tensor_lists_keep_argument_paths(self):
        a, b = tensor(1, 2), tensor(3, 4)
        nested = ([[a[0], b[0]]], [[a[1], b[1]]], ["GenericList[Tensor(float),Tensor(float)]"])
        self.assertEqual([t["path"] for t in tensor_leaves(nested, "i")], ["i:0.0", "i:0.1"])

    def test_view_and_empty_do_not_create_value_writes(self):
        a, b = tensor(1, 2), tensor(3, 2)
        result = effects("aten::view", "", io(a), io(b))
        self.assertEqual(result["category"], "alias")
        self.assertEqual((result["writes"], result["allocations"], result["reads"]), ([], [], []))
        result = effects("aten::empty", "", io(), io(a))
        self.assertEqual((result["category"], result["writes"]), ("allocate_uninitialized", []))

    def test_copy_overwrites_without_old_destination_read(self):
        a, b = tensor(1, 2), tensor(3, 4)
        schema = "aten::copy_(Tensor(a!) self, Tensor src) -> Tensor(a!)"
        result = effects("aten::copy_", schema, io(a, b), io(a))
        self.assertEqual(result["reads"], ["i:1"])
        self.assertEqual(result["writes"], ["o:0"])
        self.assertEqual(result["allocations"], [])

    def test_accumulation_reads_old_destination_and_never_allocates_it(self):
        overwrite = effects("tex_ts::te_gemm_ts", "", *te_fixture())
        accum = effects("tex_ts::te_gemm_ts", "", *te_fixture(accumulate=1))
        self.assertEqual(overwrite["reads"], ["i:0", "i:5"])
        self.assertEqual(accum["reads"], ["i:0", "i:5", "i:10"])
        self.assertEqual(accum["allocations"], [])

    def test_rebinding_and_unknown_mutation_stay_explicit(self):
        a, b = tensor(1, 2), tensor(1, 3)
        self.assertEqual(effects("aten::set_", "", io(a), io(b))["category"], "storage_rebind")
        schema = "aten::index_put_(Tensor(a!) self, Tensor[] indices) -> Tensor(a!)"
        result = effects("aten::index_put_", schema, io(a, b), io(a))
        self.assertEqual(result["potential_writes"], ["i:0"])
        self.assertEqual(result["writes"], [])
        self.assertEqual(effects("opaque", "", io(a), io(b))["category"], "unresolved")

    def test_schema_does_not_invent_tensor_memory_reads(self):
        a = tensor(1, 2)
        result = effects("aten::is_pinned", "aten::is_pinned(Tensor self) -> bool", io(a), io())
        self.assertEqual(result["operand_inputs"], ["i:0"])
        self.assertEqual(result["reads"], [])

    def test_copy_then_alias_then_accumulation_recovers_producer(self):
        state = ByteVersions()
        src = state.allocate(0, "cuda:0", 4, 32, initial="source input")
        dest = state.allocate(0, "cuda:0", 2, 32)
        a, b, view = tensor(1, 2), tensor(3, 4), tensor(5, 2)
        bind = {"i:0": AccessBinding(dest, ((0, 32),)), "i:1": AccessBinding(src, ((0, 32),)),
                "o:0": AccessBinding(dest, ((0, 32),))}
        copy = effects("aten::copy_", "aten::copy_(Tensor(a!) self, Tensor src) -> Tensor(a!)", io(a, b), io(a))
        result = apply_effect(state, copy, bind, "copy", "explicit fixture")
        self.assertEqual(result["reads"]["i:1"][0].version.producer, None)
        alias = effects("aten::view", "", io(a), io(view))
        self.assertEqual(apply_effect(state, alias, bind, "view", "fixture")["writes"], {})
        add = effects("aten::add_", "aten::add_(Tensor(a!) self, Tensor other) -> Tensor(a!)", io(view, b), io(view))
        result = apply_effect(state, add, bind, "accumulate", "fixture")
        self.assertEqual(result["reads"]["i:0"][0].version.producer, "copy")
        self.assertEqual(state.read(dest, ((0, 32),))[0].version.producer, "accumulate")

    def test_unresolved_or_mismatched_call_never_mutates_state(self):
        state = ByteVersions()
        src = state.allocate(0, "cuda:0", 4, 32)  # no initialized source
        dest = state.allocate(0, "cuda:0", 2, 32, initial="old destination")
        a, b = tensor(1, 2), tensor(3, 4)
        copy = effects("aten::copy_", "aten::copy_(Tensor(a!) self, Tensor src) -> Tensor(a!)", io(a, b), io(a))
        bind = {"i:0": AccessBinding(dest, ((0, 32),)), "i:1": AccessBinding(src, ((0, 32),)),
                "o:0": AccessBinding(dest, ((0, 32),))}
        with self.assertRaisesRegex(ValueError, "uninitialized"):
            apply_effect(state, copy, bind, "copy", "fixture")
        self.assertEqual(state.read(dest, ((0, 32),))[0].version.provenance, "old destination")
        with self.assertRaisesRegex(ValueError, "binding"):
            apply_effect(state, copy, {}, "copy", "fixture")
        with self.assertRaisesRegex(ValueError, "lowering"):
            apply_effect(state, effects("opaque", "", io(a), io(b)), bind, "opaque", "fixture")

    def test_binding_cannot_cross_a_rank_or_storage(self):
        state = ByteVersions()
        src = state.allocate(1, "cuda:0", 4, 32, initial="other rank")
        dest = state.allocate(0, "cuda:0", 2, 32)
        a, b = tensor(1, 2), tensor(3, 4)
        copy = effects("aten::copy_", "aten::copy_(Tensor(a!) self, Tensor src) -> Tensor(a!)", io(a, b), io(a))
        bind = {"i:0": AccessBinding(dest, ((0, 32),)), "i:1": AccessBinding(src, ((0, 32),)),
                "o:0": AccessBinding(dest, ((0, 32),))}
        with self.assertRaisesRegex(ValueError, "rank"):
            apply_effect(state, copy, bind, "copy", "fixture")

    def test_overwrite_cannot_replace_destination_binding(self):
        state = ByteVersions()
        src = state.allocate(0, "cuda:0", 4, 32, initial="source input")
        dest = state.allocate(0, "cuda:0", 2, 32)
        a, b = tensor(1, 2), tensor(3, 4)
        copy = effects("aten::copy_", "aten::copy_(Tensor(a!) self, Tensor src) -> Tensor(a!)", io(a, b), io(a))
        bind = {"i:0": AccessBinding(dest, ((0, 32),)), "i:1": AccessBinding(src, ((0, 32),)),
                "o:0": AccessBinding(dest, ((0, 16),))}
        with self.assertRaisesRegex(ValueError, "binding changed"):
            apply_effect(state, copy, bind, "copy", "fixture")
        with self.assertRaisesRegex(ValueError, "uninitialized"):
            state.read(dest, ((0, 16),))


if __name__ == "__main__":
    unittest.main()
