# Python modules
from typing import List, Tuple, Dict
import random
import sys
import os

# RapidChiplet modules
from rapidchiplet import generate_traffic as gt
from rapidchiplet import generate_routing as gr
from rapidchiplet import helpers as rc_hlp
from rapidchiplet import run_rapidchiplet as rrc

# Custom modules
import config as cfg
import helpers as hlp
from System import System
import analyze_topology as at

class RC_Chiplet:
    def __init__(self, w : float, h : float, typ : str, represents : str) -> None:
        self.w = w
        self.h = h
        self.typ = typ
        self.represents = represents   # "reticle" for central_router topology, "vertical_connector" for fully_connected topology

    def is_equal(self, other : 'RC_Chiplet') -> bool:
        if self.w != other.w or self.h != other.h or self.typ != other.typ or self.represents != other.represents:
            return False
        return True

def export_chiplets_to_rapidchiplet(system : System) -> Dict:
    # Gather all reticles and add the layer number as an attribute
    all_reticles = []
    for (wid, wafer) in enumerate(system.wafers):
        for ret in wafer.reticles:
            ret.attributes['layer'] = wid
            all_reticles.append(ret)
            # Currently, we only support the "fully_connected" topology for interconnect reticles. Compute reticles must use the "central_router" topology.
            if ret.typ == "compute" and ret.noc_topology != "central_router":
                hlp.register_error("Compute reticles must use the 'central_router' NoC topology for export to RapidChiplet.")
    # Transform reticles to RC_Chiplet and only keep the unique ones, and the RC chiplet ID to each reticle as an attribute
    # Since RapidChiplet does not model the intra-chiplet network, we apply a hack:
    # - Reticles with the "central_router" topology are exported as one chiplet
    # - For reticles with the "fully_connected" topology, we export one chiplet per vertical connector.
    unique_chiplets = []
    for ret in all_reticles:
        # Central router topology: one chiplet per reticle
        if ret.noc_topology == "central_router":
            w = max([x for (x,y) in ret.shape_points]) - min([x for (x,y) in ret.shape_points])
            h = max([y for (x,y) in ret.shape_points]) - min([y for (x,y) in ret.shape_points])
            chiplet = RC_Chiplet(w, h, ret.typ, "reticle")
            for (cid, existing_chiplet) in enumerate(unique_chiplets):
                if chiplet.is_equal(existing_chiplet):
                    ret.attributes['rc_chiplet_name'] = "chiplet_%d" % cid
                    break
            if not 'rc_chiplet_name' in ret.attributes:
                ret.attributes['rc_chiplet_name'] = "chiplet_%d" % len(unique_chiplets)
                unique_chiplets.append(chiplet)
        # Fully connected topology: one chiplet per vertical connector
        elif ret.noc_topology == "fully_connected":
            for (vcid, vc) in enumerate(ret.vertical_connectors):
                w, h = vc.w, vc.h
                chiplet = RC_Chiplet(w, h, ret.typ, "vertical_connector")
                for (cid, existing_chiplet) in enumerate(unique_chiplets):
                    if chiplet.is_equal(existing_chiplet):
                        if "rc_chiplet_name" not in ret.attributes:
                            ret.attributes['rc_chiplet_name'] = "chiplet_%d" % cid
                        elif ret.attributes['rc_chiplet_name'] != "chiplet_%d" % cid:
                            hlp.register_error("Reticles with the 'fully_connected' topology must have all vertical connectors of the same size, otherwise they cannot be exported to RapidChiplet.")
                        break
                if not 'rc_chiplet_name' in ret.attributes:
                    ret.attributes['rc_chiplet_name'] = "chiplet_%d" % len(unique_chiplets)
                    unique_chiplets.append(chiplet)
        # Concentration-2 topology: one chiplet per two vertical connectors 
        elif ret.noc_topology == "concentration_2":
            vc_coords = [(vc.x, vc.y) for vc in ret.vertical_connectors]
            vc_width = [vc.w for vc in ret.vertical_connectors]
            if min(vc_width) != max(vc_width):
                hlp.register_error("Reticles with the 'concentration_2' topology must have all vertical connectors of the same size, otherwise they cannot be exported to RapidChiplet.")
            vc_width = vc_width[0]
            vc_height = [vc.h for vc in ret.vertical_connectors]
            if min(vc_height) != max(vc_height):
                hlp.register_error("Reticles with the 'concentration_2' topology must have all vertical connectors of the same size, otherwise they cannot be exported to RapidChiplet.")
            vc_height = vc_height[0]
            router_coords = hlp.pair_closest(vc_coords)
            for ((x1,y1), (x2,y2)) in router_coords:
                w, h = (2 * vc_width, vc_height) if y1 == y2 else (vc_width, 2 * vc_height)
                chiplet = RC_Chiplet(w, h, ret.typ, "vertical_connector")
                for (cid, existing_chiplet) in enumerate(unique_chiplets):
                    if chiplet.is_equal(existing_chiplet):
                        if "rc_chiplet_name" not in ret.attributes:
                            ret.attributes['rc_chiplet_name'] = "chiplet_%d" % cid
                        elif ret.attributes['rc_chiplet_name'] != "chiplet_%d" % cid:
                            hlp.register_error("Reticles with the 'concentration_2' topology must have all vertical connector pairs of the same size, otherwise they cannot be exported to RapidChiplet.")
                        break
                if not 'rc_chiplet_name' in ret.attributes:
                    ret.attributes['rc_chiplet_name'] = "chiplet_%d" % len(unique_chiplets)
                    unique_chiplets.append(chiplet)
        # Unsupported topology
        else:
            hlp.register_error("Unsupported NoC topology '%s' in reticle, only 'central_router' and 'fully_connected' are supported." % ret.noc_topology)
    # Export the unique chiplets to a RapidChiplet input file
    rc_chiplets = {}
    for cid, chiplet in enumerate(unique_chiplets):
        cn = "chiplet_%d" % cid
        unit_count = 0
        if chiplet.typ == "compute":
            is_trace = system.traffic.startswith("trace-")
            unit_count = 1 if is_trace else cfg.number_of_gpcs
        elif chiplet.typ == "interconnect":
            unit_count = 0
        else:
            hlp.register_error("The unit count for chiplet type '%s' is not defined." % chiplet.typ)
        # For the central_router NoC topology, we compute the average distance from any point in the chiplet to the center of the chiplet, 
        # and use that to estimate the average latency from any unit in the chiplet to the central router.
        # For the fully_connected NoC topology, we assume that each unit has a router right next to it, so the unit_to_router_latency is 0.
        unit_to_router_latency = 0
        if chiplet.represents == "reticle":
            unit_to_router_latency = int(round(hlp.avg_distance_to_rectangle_center(chiplet.w, chiplet.h) / cfg.signal_propagation_per_cycle_mm)) # in cycles
        elif chiplet.represents == "vertical_connector":
            unit_to_router_latency = 0
        else:
            hlp.register_error("Unknown chiplet representation '%s'." % chiplet.represents)
        rc_chiplets[cn] = {
                "dimensions": {"x" : chiplet.w, "y" : chiplet.h},
                "type": chiplet.typ,
                "router_latency" : cfg.router_latency_cycles, 
                "unit_to_router_latency" : unit_to_router_latency,
                "unit_count" : unit_count,
                }
    # Return the chiplets
    return rc_chiplets

def export_placement_to_rapidchiplet(system : System) -> Dict:
    # Verify that the global reticle IDs have been assigned, it not, assign them now
    if not all("global_reticle_id" in reticle.attributes for wafer in system.wafers for reticle in wafer.reticles):
        at.add_global_reticle_ids(system)
    # Verify that the rc_chiplet_name has been assigned to each reticle (this is done in export_chiplets_to_rapidchiplet)
    if not all("rc_chiplet_name" in reticle.attributes for wafer in system.wafers for reticle in wafer.reticles):
        hlp.register_error("Missing rc_chiplet_name in some reticles. Please run export_chiplets_to_rapidchiplet(system) first.")
    # Add all chiplets to the placement file. 
    rc_placement = {"chiplets" : [], "interposer_routers" : []}
    id_to_verify = 0
    for (wid, wafer) in enumerate(system.wafers):
        for reticle in wafer.reticles:
            if reticle.attributes["global_reticle_id"] != id_to_verify:
                hlp.register_error("Global reticle IDs are not sequential, please re-run add_global_reticle_ids(system).")
            id_to_verify += 1
            # Reticles with the "central_router" topology are exported as one chiplet
            if reticle.noc_topology == "central_router":
                reticle.attributes['rc_chiplet_id'] = len(rc_placement["chiplets"])
                rc_placement["chiplets"].append({
                    "id" : len(rc_placement["chiplets"]),
                    "position" : {"x" : reticle.x, "y" : reticle.y},
                    "rotation" : 0,
                    "name" : reticle.attributes['rc_chiplet_name'],
                    "layer" : wid,
                    })
            elif reticle.noc_topology == "fully_connected":
                reticle.attributes['rc_chiplet_id'] = []
                for (vcid, vc) in enumerate(reticle.vertical_connectors):
                    reticle.attributes['rc_chiplet_id'].append(len(rc_placement["chiplets"]))
                    rc_placement["chiplets"].append({
                        "id" : len(rc_placement["chiplets"]),
                        "position" : {"x" : vc.x, "y" : vc.y},
                        "rotation" : 0,
                        "name" : reticle.attributes['rc_chiplet_name'],
                        "layer" : wid,
                        })
            elif reticle.noc_topology == "concentration_2":
                reticle.attributes['rc_chiplet_id'] = {}
                vc_coords = [(vc.x, vc.y) for vc in reticle.vertical_connectors]
                router_coords = hlp.pair_closest(vc_coords)
                for ((x1,y1), (x2,y2)) in router_coords:
                    rc_placement["chiplets"].append({
                        "id" : len(rc_placement["chiplets"]),
                        "position" : {"x" : (x1 + x2) / 2, "y" : (y1 + y2) / 2},
                        "rotation" : 0,
                        "name" : reticle.attributes['rc_chiplet_name'],
                        "layer" : wid,
                        })
                    reticle.attributes['rc_chiplet_id'][(x1,y1)] = len(rc_placement["chiplets"]) - 1
                    reticle.attributes['rc_chiplet_id'][(x2,y2)] = len(rc_placement["chiplets"]) - 1
            else:
                hlp.register_error("Unsupported NoC topology '%s' in reticle, only 'central_router' and 'fully_connected' are supported." % reticle.noc_topology)
    # Return the placement
    return rc_placement


def export_links_to_rapidchiplet(system : System) -> List:
    # Verify that the analyze_topology function has been run before the export
    if not all("neighbors" in reticle.attributes for wafer in system.wafers for reticle in wafer.reticles):
        hlp.register_error("Missing neighbor information in reticles. Please run add_neighbor_information(system) first.")
    # Verify that the global reticle IDs have been assigned, it not, assign them now
    if not all("global_reticle_id" in reticle.attributes for wafer in system.wafers for reticle in wafer.reticles):
        at.add_global_reticle_ids(system)
    # Add all links based on neighbor information.
    rc_links = []
    for (wid, wafer) in enumerate(system.wafers):
        for (rid, ret) in enumerate(wafer.reticles):
            # If this is a reticle with the "fully_connected" topology, then add all internal NoC links first
            if ret.noc_topology == "fully_connected":
                for (vcid, vc) in enumerate(ret.vertical_connectors):
                    for (ovcid, ovc) in enumerate(ret.vertical_connectors):
                        # We use bidirectional links in RapidChiplet, so only add one direction
                        if vcid < ovcid:
                            link_bw = int(round(cfg.link_bandwidth_bit_per_sec / cfg.network_frequency_hz))
                            link_len = (abs(vc.x - ovc.x) + abs(vc.y - ovc.y))
                            link_lat = int(round(link_len / cfg.signal_propagation_per_cycle_mm)) # in cycles
                            src_chiplet_id = ret.attributes["rc_chiplet_id"][vcid]
                            dst_chiplet_id = ret.attributes["rc_chiplet_id"][ovcid]
                            rc_links.append({
                                "src" : src_chiplet_id,
                                "dst" : dst_chiplet_id,
                                "bandwidth" : link_bw,
                                "latency" : link_lat,
                                "bidirectional" : True,
                                })
            # If this is a reticle concentration_2 topology, then add all internal NoC links first
            elif ret.noc_topology == "concentration_2":
                vc_coords = [(vc.x, vc.y) for vc in ret.vertical_connectors]
                router_coords = hlp.pair_closest(vc_coords)
                for i in range(len(router_coords)):
                    for j in range(i + 1, len(router_coords)):
                        ((x1a, y1a), (x2a, y2a)) = router_coords[i]
                        ((x1b, y1b), (x2b, y2b)) = router_coords[j]
                        xa, ya = (x1a + x2a) / 2, (y1a + y2a) / 2
                        xb, yb = (x1b + x2b) / 2, (y1b + y2b) / 2
                        link_bw = int(round(cfg.link_bandwidth_bit_per_sec / cfg.network_frequency_hz))
                        link_len = (abs(xa - xb) + abs(ya - yb))
                        link_lat = int(round(link_len / cfg.signal_propagation_per_cycle_mm)) # in cycles
                        src_chiplet_id = ret.attributes["rc_chiplet_id"][(x1a,y1a)]
                        dst_chiplet_id = ret.attributes["rc_chiplet_id"][(x1b,y1b)]
                        rc_links.append({
                            "src" : src_chiplet_id,
                            "dst" : dst_chiplet_id,
                            "bandwidth" : link_bw,
                            "latency" : link_lat,
                            "bidirectional" : True,
                            })
            # Add all links between different reticles
            for (owid, orid, ovcid, vcid) in ret.attributes['neighbors']:
                # Since neighbor information is bidirectional, only add the link if we are the lower ID reticle
                if (wid < owid) or (wid == owid and rid < orid):
                    vc = ret.vertical_connectors[vcid]
                    oret = system.wafers[owid].reticles[orid]
                    ovc = oret.vertical_connectors[ovcid]
                    link_bw = int(round(cfg.link_bandwidth_bit_per_sec / cfg.network_frequency_hz)) # in bits per cycle
                    link_len_in_ret = 0
                    link_len_in_oret = 0
                    src_chiplet_id = -1
                    dst_chiplet_id = -1
                    if ret.noc_topology == "central_router":
                        link_len_in_ret = abs(ret.x - vc.x) + abs(ret.y - vc.y)
                        link_len_in_oret = abs(oret.x - ovc.x) + abs(oret.y - ovc.y)
                        src_chiplet_id = ret.attributes["rc_chiplet_id"]
                    elif ret.noc_topology == "fully_connected":
                        link_len_in_ret = 0
                        link_len_in_oret = 0
                        src_chiplet_id = ret.attributes["rc_chiplet_id"][vcid]
                    elif ret.noc_topology == "concentration_2":
                        vc_coords = [(vc.x, vc.y) for vc in ret.vertical_connectors]
                        router_coords = hlp.pair_closest(vc_coords)
                        all_link_lens = [round(abs(x1 - ((x1 + x2) / 2)) + abs(y1 - ((y1 + y2) / 2)),6) for ((x1,y1), (x2,y2)) in router_coords] # Round for numerical stability
                        if min(all_link_lens) != max(all_link_lens):
                            hlp.register_error("Inconsistent length of links from vertical connectors to router in reticle with concentration_2 topology, cannot export to RapidChiplet.")
                        link_len_in_ret = min(all_link_lens)
                        vc_coords = [(vc.x, vc.y) for vc in oret.vertical_connectors]
                        router_coords = hlp.pair_closest(vc_coords)
                        all_link_lens = [round(abs(x1 - ((x1 + x2) / 2)) + abs(y1 - ((y1 + y2) / 2)),6) for ((x1,y1), (x2,y2)) in router_coords] # Round for numerical stability
                        if min(all_link_lens) != max(all_link_lens):
                            hlp.register_error("Inconsistent length of links from vertical connectors to router in reticle with concentration_2 topology, cannot export to RapidChiplet.")
                        link_len_in_oret = min(all_link_lens)
                        src_chiplet_id = ret.attributes["rc_chiplet_id"][(vc.x, vc.y)]
                    if oret.noc_topology == "central_router":
                        dst_chiplet_id = oret.attributes["rc_chiplet_id"]
                    elif oret.noc_topology == "fully_connected":
                        dst_chiplet_id = oret.attributes["rc_chiplet_id"][ovcid]
                    elif oret.noc_topology == "concentration_2":
                        dst_chiplet_id = oret.attributes["rc_chiplet_id"][(ovc.x, ovc.y)]
                    link_lat = int(round((link_len_in_ret + link_len_in_oret) / cfg.signal_propagation_per_cycle_mm + 1)) # in cycles, +1 hybrid bonding latency
                    rc_links.append({
                        "src" : src_chiplet_id,
                        "dst" : dst_chiplet_id,
                        "bandwidth" : link_bw,
                        "latency" : link_lat,
                        "bidirectional" : True,
                        })
    # Return the links
    return rc_links

def export_booksim_config(system : System, bs_params : Dict) -> Dict:

    # Differentiate between traffic patterns and traces
    traffic = system.traffic
    if traffic.startswith("trace-"):
        trace_name = traffic[6:]
        # We need to select the correct trace for a given system (correct number of GPUs)
        if trace_name == "llama7B":
            n_gpus = cfg.trace_gpu_count_map[(system.integration_level, system.wafer_diameter, system.wafer_utilization)]
        else:
            hlp.register_error("Unknown trace name '%s'." % trace_name)
        bs_mode = "trace"
        bs_traffic = "uniform"  # We need to set something valid, even if it is not used in trace mode
        bs_trace = "rapidchiplet/booksim2/src/rc_traces/%s_%d.json" % (trace_name, n_gpus)
        bs_reps = cfg.bs_repetitions   # NOTE: This can be set to 1 if we don't want to do the trace-simulations only once
        bs_sample_period = cfg.bs_cycle_limit_for_trace_simulations
    else:
        bs_mode = "traffic"
        bs_traffic = traffic
        bs_trace = "none"
        bs_reps = cfg.bs_repetitions
        bs_sample_period = 10000  # According to the sample period analysis, 10k cycles is good for our scale of networks

    # Default values for BookSim: Adjust these defaults as needed
    bs_cfg = {
        "repetitions" : bs_reps,                                    # 
        "traffic" : bs_traffic,                                     # Switch between traffic and traces; have multiple traffic patterns
        "modular_routing_function" : system.routing_function,       # Routing function
        "modular_selection_function" : system.selection_function,   # Selection function
        "seed" : "time",                                            # Use "time" as seed, otherwise, all reps are identical
        "mode": bs_mode,                                            # "traffic" or "trace"
        "ignore_cycles": 0,                                         # Model compute latency in BookSim
        "trace_time_out" : cfg.bs_trace_time_out,                   # Timeout for trace simulations
        "trace_file": bs_trace,                                     # Path of the trace file
        "precision": cfg.bs_precision,                              # 
        "saturation_factor": 2,                                     # Run until latency is 2x the minimum latency
        "num_vcs": cfg.number_of_virtual_channels,                  # Number of virtual channels
        "vc_buf_size": cfg.buffer_size_per_vc_flits,                # Buffer size per virtual channel - Similar to link latency
        "warmup_periods": 1,                                        # Number of warmup periods
        "sim_count": 1,                                             # Number of simulation periods (we do repetitions outside of BookSim)
        "hold_switch_for_packet": 0,                                # 
        "packet_size": 1,                                           # Packet size in flits
        "vc_allocator": "separable_input_first",                    # 
        "sw_allocator": "separable_input_first",                    #
        "alloc_iters": 1,                                           #
        "sample_period": bs_sample_period,                          # Sample period for simulation (abort after this many cycles)
        "wait_for_tail_credit": 0,                                  #
        "priority": "none",                                         #
        "injection_rate_uses_flits": 1,                             #
        "deadlock_warn_timeout": 200000,                            # Twice the length of the max sample period in the sample period analysis
        "time_limit" : 43200,                                       # If a single run takes longer than 12h, we abort
    }
    # Override with any user-provided parameters
    for key, value in bs_params.items():
        if key in bs_cfg:
            bs_cfg[key] = value
        else:
            hlp.register_error("Unknown BookSim parameter: %s" % key)
    return bs_cfg

def export_system_to_rapidchiplet(system : System, name : str, bs_params : Dict = {}) -> Dict:
    # Export the chiplets, placement and links
    chiplets = export_chiplets_to_rapidchiplet(system)
    placement = export_placement_to_rapidchiplet(system)
    links = export_links_to_rapidchiplet(system)
    bs_cfg = export_booksim_config(system, bs_params)
    # Create an adjacency list for routing (only needed by RapidChiplet proxies but not by BookSim)
    adj_list = rc_hlp.construct_adj_list(chiplets, placement, links)
    # The following two inputs are only needed for the RapidChiplet proxies but not for the BookSim simulation.
    # We leave them here for completeness, but for all experiments and data in the paper, they are not used.
    # Note that the configuration of traffic and routing for RapidChiplet do not cover all traces and routing algorithms supported by BookSim and used in the paper.
    traffic_by_unit, traffic_by_chiplet = gt.generate_traffic(chiplets, placement, "random_uniform", [["compute"], ["compute"]])    
    routing_table = gr.shortest_path_lowest_id_first_routing(adj_list)      
    # Collect all inputs for RapidChiplet
    rc_inputs = {}
    rc_inputs["print_prefix"] = "".join([(x[:3] if x[-2:] == "mm" else x.replace("and","&")[0].upper()) for x in name.split("_")])
    rc_inputs["name"] = name
    rc_inputs["chiplets"] = chiplets
    rc_inputs["placement"] = placement
    rc_inputs["links"] = links
    rc_inputs["booksim_config"] = bs_cfg
    rc_inputs["traffic_by_unit"] = traffic_by_unit
    rc_inputs["traffic_by_chiplet"] = traffic_by_chiplet
    rc_inputs["routing_table"] = routing_table
    # Return the inputs
    return rc_inputs

def run_rapidchiplet(system : System, do_compute : List[str], name : str) -> Dict:
    rc_inputs = export_system_to_rapidchiplet(system, name)
    rc_results = rrc.run_rapidchiplet(rc_inputs, do_compute, name, verbose = True)
    return rc_results

