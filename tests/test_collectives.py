"""Analytical collective semantics and target-resource regressions."""
from dataclasses import replace
import unittest

from wafer_sim.workloads.chakra_collectives import operands, parameter_record, init_groups, resolve_rank, match_collectives
from wafer_sim.workloads.collectives import Collective, Slot, validate, from_match
from wafer_sim.adapters.collectives import bind_collective
from wafer_sim.architecture.spatial import Target, MemoryRegion, ComputeResource, Network
from wafer_sim.execution.collectives import CollectiveState
from wafer_sim.execution.plan import Allocation
from wafer_sim.execution.reservations import ReservationPool


EVIDENCE = "Analytical semantic fixture, not an application experiment"
POLICY = "direct_exchange_rank_order_sum"
PG = "__torch__.torch.classes.c10d.ProcessGroup"
WORK = "__torch__.torch.classes.c10d.Work"


def tensor(identity, count):
    return [identity, identity+100, 0, count, 4, "cuda:0"]


def coalesced(kind="allgather", count=4, size=2):
    name = "c10d::allgather_into_tensor_coalesced_" if kind == "allgather" else "c10d::reduce_scatter_tensor_coalesced_"
    i, o = (count, count*size) if kind == "allgather" else (count*size, count)
    values = [[tensor(1, o)], [tensor(2, i)], "<Object>"]
    shapes = [[[o]], [[i]], []]
    types = ["GenericList[Tensor(float)]", "GenericList[Tensor(float)]", "Object"]
    schema = f"{name}(Tensor[] outputs, Tensor[] inputs, {PG} process_group"
    if kind == "reduce_scatter":
        values += ["<Object>", -1]; shapes += [[], []]; types += ["Object", "Int"]
        schema += ", __torch__.torch.classes.c10d.ReduceOp reduce_op, int timeout"
    schema += f") -> {WORK}"
    return name, schema, (values, shapes, types), (["<Object>"], [[]], ["Object"])


def param(kind="_allgather_base", local=0, seq=10, members=(3, 7), data=False):
    vals = [seq, ["pg", "group"], local, kind, [], [], members[0], members[1]-members[0] if len(members)>1 else 0, len(members)]
    types = ["Int", "Tuple[String,String]", "Int", "String", "GenericList[]", "GenericList[]", "Int", "Int", "Int"]
    shapes = [[] for _ in vals]
    if data:
        vals.insert(0, [tensor(1, 4)]); types.insert(0, "GenericList[Tensor(float)]"); shapes.insert(0, [[4]])
    return (vals, shapes, types)


def report(rank, local, seq=10):
    name, schema, inputs, outputs = coalesced()
    intent = operands(name, schema, inputs, outputs)
    identity = dict(parameter_record(param("allgather_into_tensor_coalesced", local, seq)), source_node=2)
    call = dict(rank=rank, node_id=1, name=name, intent=intent, identity=identity, issues=[], source_wait_nodes=[])
    return dict(rank=rank, groups=[], parameters=[dict(node_id=2, **identity)], calls=[call], errors=[])


def machine(capacity=512):
    return Target(tuple(MemoryRegion(str(r), r, capacity, f"read-{r}", f"write-{r}", EVIDENCE) for r in (3, 7, 9)),
        tuple(ComputeResource(f"compute-{r}", str(r), ("scalar_add", "mac"), EVIDENCE) for r in (3, 7, 9)),
        Network(((3, 30), (7, 70), (9, 90)), ((30, 70), (70, 90)), EVIDENCE))


def logical(kind="allgather", members=(3, 7), slots=None):
    n = len(members)
    i, o = (4*n, 4) if kind == "reduce_scatter" else (4, 4*n if kind == "allgather" else 4)
    return Collective("operation", kind, members,
        (() if kind == "barrier" else (Slot(i, o, 4, "float32"),)) if slots is None else slots,
        "sum" if kind in {"allreduce", "reduce_scatter"} else None,
        members[0] if kind == "broadcast" else None, EVIDENCE)


class SourceCollectiveTests(unittest.TestCase):
    def test_roles_separate_send_and_receive_sizes(self):
        intent = operands(*coalesced(count=5, size=16))
        self.assertEqual((intent["logical_input_bytes"], intent["logical_output_bytes"]), (20, 320))
        self.assertEqual(intent["slots"][0]["destination"]["path"], "i:0.0")
        self.assertEqual(intent["required_group_size"], 16)
        self.assertFalse(intent["cpu_return_completes_output"])

    def test_reduce_scatter_roles(self):
        intent = operands(*coalesced("reduce_scatter", 5, 16))
        self.assertEqual((intent["logical_input_bytes"], intent["logical_output_bytes"]), (320, 20))
        self.assertIsNone(intent["reduction"])

    def test_bad_ratio_rejected(self):
        name, schema, io, out = coalesced()
        io[0][0][0][3] = 7; io[1][0][0] = [7]
        with self.assertRaises(ValueError):
            operands(name, schema, io, out)

    def test_meta_not_physical_activity(self):
        name, schema, io, out = coalesced()
        io[0][0][0][5] = "meta"
        with self.assertRaises(ValueError):
            operands(name, schema, io, out)

    def test_both_parameter_abis_preserve_communicator_order(self):
        for data in (False, True):
            parsed = parameter_record(param(local=1, data=data))
            self.assertEqual(parsed["members"], [3, 7])
            self.assertEqual((parsed["sequence"], parsed["local_rank"]), (10, 1))

    def test_wait_does_not_invent_members(self):
        values, shapes, types = param("wait")
        values[-3:-1] = [-1, -1]
        self.assertIsNone(parameter_record((values, shapes, types))["members"])

    def test_duplicate_affine_participants_rejected(self):
        values, shapes, types = param()
        values[-2] = 0
        with self.assertRaises(ValueError):
            parameter_record((values, shapes, types))

    def test_missing_and_duplicate_rank_not_matched(self):
        self.assertFalse(match_collectives([report(3, 0)])["collectives"][0]["participant_and_volume_match"])
        a, b = report(3, 0), report(7, 1)
        a["calls"].append(a["calls"][0])
        self.assertFalse(match_collectives([a, b])["collectives"][0]["participant_and_volume_match"])

    def test_source_identity_not_ordinal_position(self):
        matched = match_collectives([report(3, 0, 10), report(7, 1, 11)])
        self.assertEqual(len(matched["collectives"]), 2)
        self.assertTrue(all(not c["participant_and_volume_match"] for c in matched["collectives"]))

    def test_complete_match_produces_logical_contract(self):
        reports = [report(7, 1), report(3, 0)]
        match = match_collectives(reports)["collectives"][0]
        c = from_match(match, {(r["rank"], 1):r["calls"][0] for r in reports})
        self.assertEqual(c.members, (3, 7))
        self.assertEqual(c.slots[0].output_elements, 8)

    def test_group_metadata_conflict_rejected(self):
        a, b = report(3, 0), report(7, 1)
        b["parameters"][0]["members"] = [7, 3]
        self.assertFalse(match_collectives([a,b])["collectives"][0]["participant_and_volume_match"])

    def test_coalesced_autograd_sequence_not_communication_identity(self):
        name, schema, io, out = coalesced()
        row = dict(node_id=1, name=name, byte_offset=0, source_ctrl_deps=[0], source_data_deps=[],
            attrs=dict(is_cpu_op=True, seq_id=999, op_schema=schema), inputs=io, outputs=out, is_gpu_collective=False)
        call = resolve_rank([row], 3)["calls"][0]
        self.assertIsNone(call["identity"])
        self.assertEqual(call["issues"], ["missing_or_ambiguous_group_sequence"])

    def test_volume_mismatch_across_ranks_rejected(self):
        a, b = report(3, 0), report(7, 1)
        b["calls"][0]["intent"]["slots"][0]["input_elements"] = 8
        self.assertFalse(match_collectives([a,b])["collectives"][0]["participant_and_volume_match"])


class TargetCollectiveTests(unittest.TestCase):
    def binding(self, kind="allgather", members=(3, 7), target=None, placement=None):
        return bind_collective(logical(kind, members), target or machine(),
                               placement or {r:f"compute-{r}" for r in members}, policy=POLICY)

    def entered(self, binding):
        state = CollectiveState(binding)
        self.assertTrue(state.pool.reserve(binding.inputs.values()))
        ready = set(a.key for a in binding.inputs.values())
        for rank in binding.collective.members:
            self.assertTrue(state.enter(rank, ready))
        return state

    def drain(self, state):
        while not state.all_complete():
            ready = state.ready_actions()
            self.assertTrue(ready)
            for action in ready:
                state.begin(action); state.complete(action)

    def test_direct_allgather_bytes(self):
        b = self.binding(members=(3,7,9))
        self.assertEqual(sum(a.phase.transfer.size_bytes for a in b.actions.values() if a.phase.transfer), 3*2*16)
        self.assertEqual(len(b.output_requirements), 3)

    def test_transfer_finish_is_not_destination_ready(self):
        b = self.binding()
        state = self.entered(b)
        for name in ["0/read/3", "0/3->7/network"]:
            state.begin(name); state.complete(name)
        self.assertFalse(state.output_ready(7,0))
        self.assertFalse(state.wait_satisfied(7))
        self.drain(state)
        self.assertTrue(state.output_ready(7,0))
        self.assertTrue(state.wait_satisfied(7))

    def test_send_requires_destination_entry(self):
        b = self.binding(); state = CollectiveState(b)
        state.pool.reserve(b.inputs.values())
        state.enter(3, {a.key for a in b.inputs.values()})
        state.begin("0/read/3"); state.complete("0/read/3")
        with self.assertRaises(ValueError):
            state.begin("0/3->7/network")

    def test_reduction_work_and_staging_lifetime(self):
        b = self.binding("allreduce", (3,7,9)); state = self.entered(b)
        self.assertEqual(sum(d.amount for a in b.actions.values() for d in a.phase.demands if d.unit=="scalar_add"), 8)
        self.assertEqual(sum(a.phase.transfer.size_bytes for a in b.actions.values() if a.phase.transfer), 4*16)
        self.assertTrue(any(k[0]=="collective_stage" for k in state.pool.allocations))
        self.drain(state)
        self.assertFalse(any(k[0]=="collective_stage" for k in state.pool.allocations))
        self.assertTrue(all(a.key in state.pool.allocations for a in b.outputs.values()))

    def test_reduce_scatter_reads_all_chunks_once(self):
        b = self.binding("reduce_scatter", (3,7,9))
        self.assertEqual(sum(a.phase.transfer.size_bytes for a in b.actions.values() if a.phase.transfer), 3*2*16)
        self.assertEqual(sum(d.amount for a in b.actions.values() for d in a.phase.demands if d.unit=="scalar_add"), 3*2*4)
        self.drain(self.entered(b))

    def test_colocated_participants_do_not_use_network(self):
        b = self.binding(placement={3:"compute-3",7:"compute-3"})
        self.assertFalse(any(a.phase.transfer for a in b.actions.values()))
        self.drain(self.entered(b))

    def test_capacity_block_is_atomic_and_recoverable(self):
        b = self.binding(target=machine(64)); state = CollectiveState(b)
        state.pool.reserve(b.inputs.values())
        hold = Allocation(("other-operation",), "3", 32)
        self.assertTrue(state.pool.reserve((hold,)))
        before = state.pool.used.copy()
        ready = {a.key for a in b.inputs.values()}
        self.assertFalse(state.enter(3, ready))
        self.assertEqual(state.pool.used, before)
        state.pool.release(hold.key)
        self.assertTrue(state.enter(3, ready))

    def test_shared_pool_limits_collectives(self):
        a = self.binding(target=machine(64)); b = bind_collective(replace(logical(), id="other"), machine(64),
            {3:"compute-3",7:"compute-7"}, policy=POLICY)
        pool = ReservationPool(a.memory)
        pool.reserve((*a.inputs.values(), *b.inputs.values()))
        first, second = CollectiveState(a, pool), CollectiveState(b, pool)
        first.enter(3, set(pool.allocations))
        self.assertFalse(second.enter(3, set(pool.allocations)))

    def test_barrier_requires_every_entry(self):
        state = CollectiveState(self.binding("barrier"))
        state.enter(3, set())
        self.assertFalse(state.wait_satisfied(3))
        state.enter(7, set())
        self.assertTrue(state.wait_satisfied(3))

    def test_unknown_reduction_and_unreachable_mapping_fail(self):
        with self.assertRaises(ValueError):
            validate(replace(logical("allreduce"), reduction=None))
        t = machine()
        with self.assertRaises(ValueError):
            self.binding(target=replace(t, network=replace(t.network, router_links=())))

    def test_input_readiness_and_duplicate_completion_checked(self):
        b = self.binding(); state = CollectiveState(b)
        with self.assertRaises(ValueError):
            state.enter(3, set())
        state = self.entered(b)
        state.begin("0/read/3"); state.complete("0/read/3")
        with self.assertRaises(ValueError):
            state.complete("0/read/3")

    def test_broadcast_root_and_local_groups(self):
        self.drain(self.entered(self.binding("broadcast")))
        for kind in ("allgather", "allreduce", "reduce_scatter", "broadcast"):
            b = self.binding(kind, (3,))
            self.assertFalse(any(a.phase.transfer for a in b.actions.values()))
            self.drain(self.entered(b))


if __name__ == "__main__":
    unittest.main()
