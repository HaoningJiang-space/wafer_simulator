"""One fixed-work/mapping-policy WoW pair with native online execution."""
from dataclasses import asdict
import json
from pathlib import Path

from wafer_sim.adapters import wow
from wafer_sim.adapters.online_booksim import OnlineBookSim,prepare_online_config
from wafer_sim.adapters.spatial import bind
from wafer_sim.adapters.transformer import place_block
from wafer_sim.adapters.wow_target import build_wow_target
from wafer_sim.analysis.online_network import audit_messages
from wafer_sim.analysis.timing import audit
from wafer_sim.analysis.timed_attribution import critical_chain,message_summary
from wafer_sim.execution.timing import execute
from wafer_sim.experiments.network_reference import compare_reference
from wafer_sim.workloads.transformer import build_block
from wafer_sim.io import read_json,write_json,object_digest


def run_placement(config, workload_config, root, runtime_root, method):
    directory=Path(root)/method
    directory.mkdir(exist_ok=False)
    inputs,endpoints,resources=wow.export_placement(Path(runtime_root)/"upstream/nw-design-for-wsi",
        directory,method,config["wafer_diameter_mm"],config["wafer_utilization"])
    if resources["network_frequency_hz"] != config["network_frequency_hz"]:
        raise ValueError("Network clock differs from registered cycles")
    exported=read_json(directory/"network.json")
    cm={k:workload_config[k] for k in ("region_capacity_bytes","compute_rates","memory_bytes_per_cycle")}
    cm["scope"]="Common analytical compute/memory; not calibrated to WoW"
    target,timing,contract=build_wow_target(exported,cm,config["flit_bytes"])
    block=build_block(**workload_config["block"])
    mapping=wow.rank_mapping(endpoints,block.dimensions["shards"],config["mapping"])
    placement=place_block(block,mapping)
    binding=bind(block.workload,target,placement)
    native_config=prepare_online_config(inputs,directory,config["network_seed"])
    client=OnlineBookSim(Path(runtime_root)/"build/booksim-online/online_booksim",native_config,
                        directory,flit_bytes=config["flit_bytes"])
    try:
        native=json.loads(json.dumps(execute(binding,timing,network=client,cycle_limit=config["cycle_limit"])))
        if not native["complete"]: raise ValueError("Target block incomplete")
        network_record=client.close()
    finally:
        client.abort()
    checked=audit(binding,timing,native)
    network_checked=audit_messages(target.network,native["network_messages"])
    reference=compare_reference(inputs,directory,directory/"standalone_reference",
        Path(runtime_root)/"build/booksim/rapidchiplet/booksim2/src/booksim",native["network_messages"],config["network_seed"])
    coarse=json.loads(json.dumps(execute(binding,timing)))
    coarse_checked=audit(binding,timing,coarse)
    record=dict(placement=method,logical_workload=asdict(block.workload),tensors=block.tensors,
        operators=block.operators,collectives=block.collectives,mapping=asdict(placement),
        worker_endpoints=mapping,worker_locations=[endpoints[e] for e in mapping],
        target=asdict(target),timing=asdict(timing),resource_contract=contract,
        network_resources=resources,booksim=native,store_and_forward=coarse,
        audit=checked,network_audit=network_checked,coarse_audit=coarse_checked,
        standalone_reference=reference,native_close=network_record["final"])
    write_json(directory/"execution.json",record)
    chain=critical_chain(binding,native)
    write_json(directory/"critical_chain.json",chain)
    messages=message_summary(native["network_messages"])
    write_json(directory/"messages.json",messages)
    collective_times={c["operation"]:dict(native["operations"][c["operation"]],
        duration=native["operations"][c["operation"]]["finish"]-native["operations"][c["operation"]]["admitted"])
        for c in block.collectives}
    summary=dict(placement=method,booksim_cycles=native["application_cycles"],
        coarse_cycles=coarse["application_cycles"],critical_chain_cycles=chain["cycles"],
        collectives=collective_times,messages=messages,network_resources=resources,
        worker_endpoints=mapping,worker_locations=[endpoints[e] for e in mapping],
        peak_bytes=native["peak_bytes"],network_audit=network_checked,
        audit=checked,standalone_reference=reference,
        logical_identity=object_digest(dict(workload=asdict(block.workload),tensors=block.tensors,
                                           operators=block.operators,collectives=block.collectives)),
        compute_memory_identity=object_digest(cm))
    write_json(directory/"SUMMARY.json",summary)
    return summary
