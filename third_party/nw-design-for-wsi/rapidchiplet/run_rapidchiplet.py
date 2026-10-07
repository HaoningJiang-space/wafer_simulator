# Import python libraries
import sys
import copy
import math
import time
import argparse

# Import RapidChiplet files
from . import helpers as hlp
from . import booksim_wrapper as bsw
from . import visualizer as vis

def compute_link_latencies(inputs):
    # User info
    hlp.print("Computing link latencies...") if inputs["verbose"] else None
    # Extract inputs
    links = inputs["links"]
    # Construct a map that maps (src_chiplet_id,dst_chiplet_id) pairs to latencies
    link_latencies = {}
    for link in links:
        src = link["src"]
        dst = link["dst"]
        lat = link["latency"]
        pairs = [(src,dst),(dst,src)] if link["bidirectional"] else [(src,dst)]
        # If multiple links exist between the same pair of chiplets, take the min latency
        for pair in pairs:
            if pair in link_latencies:
                link_latencies[pair] = min(link_latencies[pair], lat)
            else:
                link_latencies[pair] = lat
    return link_latencies

def compute_link_bandwidths(inputs):
    # User info
    hlp.print("Computing link bandwidths...") if inputs["verbose"] else None
    # Extract inputs
    links = inputs["links"]
    # Construct a map that maps (src_chiplet_id,dst_chiplet_id) pairs to bandwidths
    global link_bandwidths
    link_bandwidths = {}
    for link in links:
        src = link["src"]
        dst = link["dst"]
        bw = link["bandwidth"]
        pairs = [(src,dst),(dst,src)] if link["bidirectional"] else [(src,dst)]
        # If multiple links exist between the same pair of chiplets, take the sum bandwidth
        for pair in pairs:
            if pair in link_bandwidths:
                link_bandwidths[pair] += bw
            else:
                link_bandwidths[pair] = bw
    return link_bandwidths

def compute_latency(inputs):
    # Extract inputs
    chiplets = inputs["chiplets"]
    placement = inputs["placement"]
    links = inputs["links"]
    traffic_by_chiplet = inputs["traffic_by_chiplet"]
    routing_table_type = inputs["routing_table"]["type"]
    routing_table = inputs["routing_table"]["table"]
    # Compute intermediates
    link_latencies = compute_link_latencies(inputs)
    # User info 
    hlp.print("Computing latency...") if inputs["verbose"] else None
    # Iterate through all communicating chiplet pairs and compute the latency
    min_latency = float("inf")
    max_latency = -float("inf")
    sum_of_weghted_latencies = 0
    sum_of_weights = 0
    for (src, dst) in traffic_by_chiplet.keys():
        lat = chiplets[placement["chiplets"][src]["name"]]["unit_to_router_latency"]    # Latency from source unit to first router
        lat += chiplets[placement["chiplets"][src]["name"]]["router_latency"]           # Latency through source router
        prv = "-1"
        cur = src
        while cur != dst:
            if routing_table_type == "default":
                nxt = routing_table[cur][dst]
            elif routing_table_type == "extended":
                nxt = routing_table[cur][dst][prv]
            else:
                hlp.print("ERROR: Unknown routing table type %s" % routing_table_type)
                sys.exit(1)    
            if (cur,nxt) in link_latencies:
                lat += link_latencies[(cur,nxt)]                                        # Latency through the link
            else:
                hlp.print("ERROR: No link latency found for link (%s,%s)" % (cur,nxt))
                sys.exit(1)
            if nxt != dst:
                lat += chiplets[placement["chiplets"][nxt]["name"]]["router_latency"]   # Latency through intermediate router
            prv = cur
            cur = nxt
        lat += chiplets[placement["chiplets"][dst]["name"]]["router_latency"]           # Latency through destination router
        lat += chiplets[placement["chiplets"][dst]["name"]]["unit_to_router_latency"]   # Latency from last router to destination unit
        # Update min, max, and avg
        min_latency = min(min_latency, lat)
        max_latency = max(max_latency, lat)
        sum_of_weghted_latencies += lat * traffic_by_chiplet[(src,dst)]
        sum_of_weights += traffic_by_chiplet[(src,dst)]
    avg_latency = sum_of_weghted_latencies / sum_of_weights
    latency = {"min": min_latency, "avg": avg_latency, "max": max_latency}
    return latency

def compute_throughput(inputs):
    # Extract inputs
    chiplets = inputs["chiplets"]
    placement = inputs["placement"]
    links = inputs["links"]
    traffic_by_chiplet = inputs["traffic_by_chiplet"]
    routing_table_type = inputs["routing_table"]["type"]
    routing_table = inputs["routing_table"]["table"]
    # Compute intermediates
    link_bandwidths = compute_link_bandwidths(inputs)
    # User info
    hlp.print("Computing throughput...") if inputs["verbose"] else None
    # Initialize link loads with zero
    link_loads = {(src,dst): 0 for (src,dst) in link_bandwidths.keys()}
    # Iterate through communicating chiplets and add link-loads on the path
    for (src, dst) in traffic_by_chiplet.keys():
        prv = "-1"
        cur = src
        while cur != dst:
            if routing_table_type == "default":
                nxt = routing_table[cur][dst]
            elif routing_table_type == "extended":
                nxt = routing_table[cur][dst][prv]
            else:
                hlp.print("ERROR: Unknown routing table type %s" % routing_table_type)
                sys.exit(1)    
            # Add the traffic load to the link
            if (cur,nxt) in link_loads:
                link_loads[(cur,nxt)] += traffic_by_chiplet[(src,dst)]
            # Move to the next node
            prv = cur
            cur = nxt
    # Find the link-throughputs     
    link_throughputs = {link : (link_bandwidths[link] / link_loads[link]) if link_loads[link] > 0 else float("inf") for link in link_loads.keys()}
    # Global bottleneck throughput per unit traffic is min over used links
    min_throughput_per_traffic_unit = min(link_throughputs.values())    
    aggregate_load = sum(traffic_by_chiplet.values())
    # Compute the aggregate throughput in bits/cycle
    aggregate_throughput = min_throughput_per_traffic_unit * aggregate_load
    # Aggregate results
    throughput = {
        "aggregate_throughput" : aggregate_throughput,
    }
    # Return results
    return throughput

def perform_booksim_simulation(inputs):
    run_identifier = inputs["name"]
    # Extract inputs
    booksim_config = inputs["booksim_config"]
    booksim_reps = booksim_config["repetitions"]
    del booksim_config["repetitions"]
    # Compute intermediates
    link_latencies = compute_link_latencies(inputs)
    # Repeat the BookSim simulation if needed
    results = []
    for rep in range(booksim_reps):
        # User info
        hlp.print("Performing BookSim simulation repetition %d of %d..." % ((rep + 1), booksim_reps)) if inputs["verbose"] else None
        # Export the design to BookSim
        port_map = bsw.export_booksim_topology(inputs, link_latencies, run_identifier)
        bs_results = bsw.run_booksim_simulation(inputs, run_identifier)
        # Store a checkpoint of the results
        cp_file = "rapidchiplet/checkpoints/%s_checkpoints.jsonl" % run_identifier
        cp = {
            "timestamp" : time.strftime("%Y%m%d-%H%M%S"),
            "run_identifier" : run_identifier,
            "repetition" : rep,
            "booksim_config" : booksim_config,
            "results" : bs_results,
        }
        hlp.write_or_append_jsonl(cp_file, [cp])
        # Identify saturation throughput and zero-load latency for easy access, e.g. when computing the power
        summary = {"zero_load_latency" : float("nan"),"saturation_throughput" : float("nan")}
        all_valid_loads = [float(load) for load in bs_results.keys() if (hlp.is_float(load) and bs_results[load]["status"] == "Success" and "packet_latency" in bs_results[load].keys())]
        has_trace_results = "trace" in bs_results.keys()
        # This was a trace-based simulation, so no load sweep
        # In this scenario, we cannot identify the zero-load latency because the load is given by the trace
        # We also cannot identify the saturation throughput as again, throughput depends on the trace
        # We set these two values to the average latency / throughput for the subsequent code not to break
        # WARNING: Keep in mind that the power computation based on these values is not accurate!!!
        if has_trace_results and len(all_valid_loads) == 0:
            summary["zero_load_latency"] = bs_results["trace"]["flit_latency"]["avg"]
            summary["saturation_throughput"] = bs_results["trace"]["accepted_flit_rate"]["avg"]
        # This was a synthetic traffic pattern with load sweep
        elif not has_trace_results and len(all_valid_loads) > 0:
            min_load = min(all_valid_loads)
            max_load = max(all_valid_loads)
            summary["zero_load_latency"] = bs_results[str(min_load)]["packet_latency"]["avg"]
            summary["saturation_throughput"] = max_load 
        # Unexpected case
        else:
            hlp.print("ERROR: BookSim results contain load sweep results and trace results simultaneously.")
            sys.exit(1)
        # Add the results of this repetition to the list of results
        results.append({"summary" : summary, "detailed" : bs_results})
    # Return the results
    return results

def run_rapidchiplet(inputs, do_compute, results_file, verbose = False):
    # Store verbose option in inputs
    inputs["verbose"] = verbose
    # Store the print prefix if given
    if "print_prefix" in inputs:
        hlp.set_print_prefix(inputs["print_prefix"])
    # Initialize outputs
    outputs = {}
    # Compute the selected metrics
    for metric in do_compute:
        if metric in metric_computation_functions:
            outputs[metric] = metric_computation_functions[metric](inputs)
        else:
            hlp.print("ERROR: Unknown metric %s" % metric)
            sys.exit(1)
    return outputs

# Define all functions that compute the metrics and the metrics themselves
metric_computation_functions = {
    "latency" : compute_latency,
    "throughput" : compute_throughput,
    "booksim_simulation" : perform_booksim_simulation,
    "visualization" : vis.visualize,
}
