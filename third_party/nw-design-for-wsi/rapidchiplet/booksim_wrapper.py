# Import python libraries
import os
import sys
import math
import time
import copy
import subprocess

# Import RapidChiplet files
from . import helpers as hlp

return_codes = {
    0: "Success",
    1: "Potential Deadlock",
    2: "Unstable simulation",
    3: "Time limit exceeded"
}

def check_cdg(out_string):
    """
    Checks the multi-line string 'out_string' for the text "CDG CHECK".
    Sets cdg_check to the line containing the text or "unknown" if not found.
    """
    # Split the string into individual lines
    lines = out_string.split('\n')

    # Initialize cdg_check to the default value
    cdg_check = "unknown"

    # Iterate through the lines
    for line in lines:
        # Use 'in' to check for the substring
        if "CDG CHECK" in line:
            # If found, set cdg_check to that line and stop searching
            cdg_check = line
            break  # Exit the loop once the line is found

    return cdg_check

def execute_booksim(exec_path, config_path, time_limit, exec_identifier, logs_dir, verbose=False):
    # Execute BookSim
    start_time = time.monotonic()
    proc = subprocess.Popen([exec_path, config_path],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    writ_log = False
    result = {}
    ret = 0
    out = ""
    err = ""
    # Try to read the output within the time limit
    try:
        out, err = proc.communicate(timeout=time_limit)
        ret = proc.returncode
        runtime = time.monotonic() - start_time
        hlp.print("BookSim execution of %s completed in %.3f seconds -> %s" % (exec_identifier, runtime, return_codes.get(ret, "Unknown return code %d" % ret))) if verbose else None
        result["return_code"] = ret
        result["status"] = return_codes.get(ret, "Unknown return code %d" % ret)
        result["runtime"] = runtime
        # See if the CDG checker was enabled an if so, store its results
        result["cdg_check"] = check_cdg(out)
        # Parse and store results
        result.update(read_booksim_results(out))
        write_log = (ret not in [0,2])  # Write log files only if the simulation failed (deadlock or other error)
    # If the time limit is exceeded, kill the process and store partial output
    except subprocess.TimeoutExpired:
        proc.kill()
        hlp.print("BookSim execution of %s exceeded time limit of %ds and was killed" % (exec_identifier, time_limit)) if verbose else None
        out, err = proc.communicate()
        runtime = time.monotonic() - start_time
        write_log = True
        ret = 4
        result["return_code"] = ret
        result["status"] = "Time limit of %ds exceeded" % time_limit
        result["runtime"] = runtime
        result["cdg_check"] = "unknown"
    # Store the output and error messages in log files if the simulation failed
    if write_log:
        # Create log directory if it does not exist yet
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)
        # Prepare log files
        stdout_file = logs_dir + "/" + exec_identifier + "_stdout.log"
        stderr_file = logs_dir + "/" + exec_identifier + "_stderr.log"
        # Store logs
        with open(stdout_file, "w") as file:
            file.write(out)
        with open(stderr_file, "w") as file:
            file.write(err)
    # Print errors to console if the simulation failed (deadlock or time limit) but do not print anything if successful or unstable
    if verbose and ret not in [0,2]:
        hlp.print("----- Start of BookSim output -----")
        hlp.print("Return code: %d (%s)" % (ret, return_codes.get(ret, "Unknown return code %d" % ret)))
        hlp.print("----- BookSim output (stdout) -----")
        hlp.print("\n".join(out.splitlines()[-50:]))
        hlp.print("----- BookSim errors (stderr) -----")
        hlp.print("\n".join(err.splitlines()[-50:]))
        hlp.print("----- End of BookSim output -----")
    # Return the results
    return result

# Export the BookSim configuration file
def export_booksim_config(inputs, run_identifier, load):
    # Extract inputs
    booksim_config = inputs["booksim_config"]
    chiplets = inputs["chiplets"]
    placement = inputs["placement"]
    routing_table_type = inputs["routing_table"]["type"]
    # Prepare the BookSim configuration file for export
    bsc = copy.deepcopy(booksim_config)
    # Remove parameters that are used by RapidChiplet and not by BookSim
    del bsc["time_limit"]
    del bsc["precision"]
    del bsc["saturation_factor"]
    # Determine router latency used in BookSim. This can be set manually in the BookSim configuration file
    # If not specified, the average latency of chiplet-internal-routers and interposer-routers is used
    if "router_latency" in bsc:
        router_latency = bsc["router_latency"]
        del bsc["router_latency"]
    else:
        router_latencies = [chiplets[x["name"]]["router_latency"] for x in placement["chiplets"]]
        router_latency = int(math.ceil(sum(router_latencies) / len(router_latencies)))
        if len(set(router_latencies)) > 1:    
            hlp.print("WARNING: In BookSim simulations, all routers (on-chip or on-interposer) have the same latency. " + \
              "In your configuration, these latencies are not identical. RapidChiplet will use the average " + \
              "latency which is %d cycles. To manually set the router-latency, " % router_latency + \
              "specify the parameter \"router_latency\" in the booksim-config input file.")
    # 1) Simulation parameters
    bsc["topology"] = "anynet" 
    bsc["network_file"] = "rapidchiplet/booksim2/src/rc_topologies/%s.anynet" % run_identifier          # NOTE: path relative to parent directory
    bsc["injection_rate"] = 1.0 if bsc["mode"] == "trace" else load
    # 3) Parameters related to the timing/latencies:
    bsc["credit_delay "] = 0
    bsc["routing_delay "] = 0
    bsc["vc_alloc_delay "] = 1
    bsc["sw_alloc_delay "] = 1
    bsc["st_final_delay "] = max(1, router_latency - 2)
    bsc["input_speedup "] = 1
    bsc["output_speedup "] = 1
    bsc["internal_speedup "] = (1.0 if router_latency >= 3 else (3.0 / router_latency))
    # 4) More simulation parameters
    bsc["use_read_write "] = 0
    bsc["routing_function "] = "modular_routing"
    bsc["path_for_stats"] = "rapidchiplet/booksim2/src/rc_stats/%s_%f.csv" % (run_identifier, load)     # NOTE: path relative to parent directory
    bsc["path_for_xy_info"] = "rapidchiplet/booksim2/src/rc_xy_info/%s.csv" % (run_identifier)          # NOTE: path relative to parent directory
    # Convert configuration file to correct format
    config_lines = [(key + " = " + str(bsc[key]) + ";") for key in bsc]
    # Store the file
    save_path = "rapidchiplet/booksim2/src/rc_configs/%s.conf" % run_identifier                         #NOTE: path relative to parent directory
    with open(save_path, "w") as file:
        for line in config_lines:
            file.write(line + "\n")

def export_nighbors_for_xy_routing(inputs, run_identifier):
    placement = inputs["placement"]
    chiplets = inputs["chiplets"]
    links = inputs["links"]
    # Line-ID is the router ID, the four entries are north, east, south and west neighbor router IDs
    neighbor_lines = []
    # Map for quick access to chiplet locations
    chiplet_locations = {cid : (chiplet_desc["position"]["x"], chiplet_desc["position"]["y"]) for (cid, chiplet_desc) in enumerate(placement["chiplets"])}
    chiplet_typs = {cid : chiplets[chiplet_desc["name"]]["type"] for (cid, chiplet_desc) in enumerate(placement["chiplets"])}
    ycols = sorted(list(set([round(chiplet_locations[cid][1]) for cid in chiplet_locations if chiplet_typs[cid] == "compute"])))
    chiplet_row_ids = {cid : ycols.index(round(chiplet_locations[cid][1])) for cid in chiplet_locations if chiplet_typs[cid] == "compute"}
    xcols = sorted(list(set([round(chiplet_locations[cid][0]) for cid in chiplet_locations if chiplet_typs[cid] == "compute"])))
    chiplet_col_ids = {cid : xcols.index(round(chiplet_locations[cid][0])) for cid in chiplet_locations if chiplet_typs[cid] == "compute"}
    # Adjacency list
    adj_list = [[] for _ in range(len(placement["chiplets"]))]
    for link in links:
        src_cid = link["src"]
        dst_cid = link["dst"]
        # Bidirectional links
        if dst_cid not in adj_list[src_cid]:
            adj_list[src_cid].append(dst_cid)
        if src_cid not in adj_list[dst_cid]:
            adj_list[dst_cid].append(src_cid)
    # Write one line per chiplet with two entries being the x and y coordinates and four entries being neighbors in N, E, S, W direction (router IDs)
    lines_neighbors = []
    for (cid, (x, y)) in chiplet_locations.items():
        candidates = adj_list[cid]
        cand_per_dir = {}
        cand_per_dir["N"] = [oid for oid in candidates if chiplet_locations[oid][1] > y]
        cand_per_dir["E"] = [oid for oid in candidates if chiplet_locations[oid][0] > x]
        cand_per_dir["S"] = [oid for oid in candidates if chiplet_locations[oid][1] < y]
        cand_per_dir["W"] = [oid for oid in candidates if chiplet_locations[oid][0] < x]
        line = [str(x), str(y)]
        for direction in ["N","E","S","W"]:
            if len(cand_per_dir[direction]) == 0:
                line.append("-1") 
            elif len(cand_per_dir[direction]) == 1:
                line.append(str(cand_per_dir[direction][0]))
            elif len(cand_per_dir[direction]) == 2:
                a, b = cand_per_dir[direction]
                dist_a = math.sqrt((chiplet_locations[a][0] - x)**2 + (chiplet_locations[a][1] - y)**2)
                dist_b = math.sqrt((chiplet_locations[b][0] - x)**2 + (chiplet_locations[b][1] - y)**2)
                # If on is closer than the other, pick that one (that is used for interconnect reticles)
                if dist_a < dist_b:
                    line.append(str(a))
                elif dist_b < dist_a:
                    line.append(str(b))
                # If both are at the same distance, pick based on coordinate (that is used for compute reticles)
                # This needs to be delicately handled to avoid potential deadlocks
                else:
                    if chiplet_typs[cid] != "compute":
                        hlp.print("ERROR: This part of the code is only expected to be reached for compute reticles.")
                        sys.exit(1)
                    reticle_mirror = (chiplet_row_ids[cid] % 2) != (chiplet_col_ids[cid] % 2)
                    direction_mirror = direction in ["E","S"]
                    orthogonal_direction = 1 if direction in ["E","W"] else 0
                    mirror = reticle_mirror ^ direction_mirror
                    if chiplet_locations[a][orthogonal_direction] < chiplet_locations[b][orthogonal_direction]:
                        line.append(str(a) if not mirror else str(b))
                    elif chiplet_locations[b][orthogonal_direction] < chiplet_locations[a][orthogonal_direction]:
                        line.append(str(b) if not mirror else str(a))
                    else:
                        hlp.print("ERROR: Chiplet %d has two neighbors at the same distance in %s direction, which are both equally valid for XY routing." % (cid, direction))
                        sys.exit(1)
            else:
                hlp.print("ERROR: Chiplet %d has multiple neighbors in %s direction, which is not supported by XY routing." % (cid, direction))
                sys.exit(1)
        neighbor_lines.append(",".join(line))
    # Store neighbor_lines as csv file
    save_path = "rapidchiplet/booksim2/src/rc_xy_info/%s.csv" % run_identifier #NOTE: path relative to parent directory
    with open(save_path, "w") as file:
        for line in neighbor_lines:
            file.write(line + "\n")

# Write the BookSim topology file
# Node-IDs are consecutive starting units of chiplet 0 to units of chiplet c-1
def export_booksim_topology(inputs, link_latencies, run_identifier):
    # Extract inputs
    chiplets = inputs["chiplets"]
    placement = inputs["placement"]
    links = inputs["links"]
    n_chiplets = len(placement["chiplets"])
    # Construct adjacency list
    adj_list = hlp.construct_adj_list(chiplets, placement, links)
    # Create the topology input file for BookSim
    topology_lines = []
    # In addition, construct a port map: {(cur_type, cur_id) -> {(next_type, next_id) -> port}}
    # This map is later used to construct the routing table
    port_map = {}
    # Write one line per chiplet (central router -> nodes -> links to other routers)
    running_node_id_counter = 0
    for (cid, chiplet_desc) in enumerate(inputs["placement"]["chiplets"]):
        chiplet = chiplets[chiplet_desc["name"]]
        # The chiplets central router
        line = "router % d" % cid
        port_map_entry = {}
        # Add nodes (ports 0 to u-1 for u units)
        for uid in range(chiplet["unit_count"]):
            line += " node %d %d" % (running_node_id_counter, chiplet["unit_to_router_latency"])
            port_map_entry[("unit",running_node_id_counter)] = uid
            running_node_id_counter += 1
        # Add links to other routers
        for (cnt, oid) in enumerate(adj_list[cid]):
            lat = link_latencies[(cid,oid)]
            line += " router %d %d" % (oid, lat)
            port_map_entry[("chiplet",oid)] = chiplet["unit_count"] + cnt
        topology_lines.append(line)
        port_map[("chiplet",cid)] = port_map_entry
    # Store the file
    save_path = "rapidchiplet/booksim2/src/rc_topologies/%s.anynet" % run_identifier #NOTE: path relative to parent directory
    with open(save_path, "w") as file:
        for line in topology_lines:
            file.write(line + "\n")
    # If necessary, export the neighbor file for XY routing
    if inputs["booksim_config"]["modular_routing_function"] == "xy":
        export_nighbors_for_xy_routing(inputs, run_identifier)
    # Return the port map
    return port_map

# Read the BookSim results
def read_booksim_results(out):
    result_lines = out.split("\n")[-35:]
    metrics = ["Packet latency","Network latency","Flit latency","Fragmentation","Injected packet rate","Accepted packet rate","Injected flit rate","Accepted flit rate"]
    results = {}
    for (line_idx, line) in enumerate(result_lines):
        for metric in metrics:
            if (metric + " average") in line:
                key = metric.lower().replace(" ","_")
                key_length = len(key.split("_"))    
                results[key] = {}
                results[key]["avg"] = float(result_lines[line_idx].split(" ")[key_length + 2]) if len(result_lines[line_idx].split(" ")) > key_length + 2 else float("nan")
                results[key]["min"] = float(result_lines[line_idx+1].split(" ")[2]) if len(result_lines[line_idx+1].split(" ")) > 2 else float("nan")
                results[key]["max"] = float(result_lines[line_idx+2].split(" ")[2])    if len(result_lines[line_idx+2].split(" ")) > 2 else float("nan")
        if "Injected packet size average" in line:
            results["injected_packet_size"] = {}
            results["injected_packet_size"]["avg"] = float(line.split(" ")[5])
        if "Accepted packet size average" in line:
            results["accepted_packet_size"] = {}
            results["accepted_packet_size"]["avg"] = float(line.split(" ")[5])
        if "Hops average" in line:
            results["hops"] = {}
            results["hops"]["avg"] = float(line.split(" ")[3])
        if "Total run time" in line:
            results["total_run_time"] = float(line.split(" ")[3])
        if "Total cycles until trace completion" in line:
            results["total_run_time_cycles"] = float(line.split(" ")[6])
        if "Truly simulated cycles" in line:
            results["truly_simulated_cycles"] = float(line.split(" ")[4])
        if "Total number of trace messages simulated" in line:
            results["total_trace_messages"] = int(line.split(" ")[7])
        if "Total number of trace instructions simulated" in line:
            results["total_trace_instructions"] = int(line.split(" ")[7])
    return results

# Run a BookSim simulation:
# This runs the C++ code which needs to be built manually by executing "make" in the "booksim2/src" directory
def run_booksim_simulation(inputs, run_identifier):
    # Extract inputs
    booksim_config = inputs["booksim_config"]
    # Configuration
    time_limit = booksim_config["time_limit"]
    precision = booksim_config["precision"]
    saturation_factor = booksim_config["saturation_factor"]
    # Paths
    exec_path = "rapidchiplet/booksim2/src/booksim" # NOTE: path relative to parent directory
    config_path = "rapidchiplet/booksim2/src/rc_configs/%s.conf" % run_identifier # NOTE: path relative to parent directory
    # Prepare the results
    results = {}
    # Traffic mode: Iterate through loads
    if booksim_config["mode"] == "traffic":
        decimal_places = max(0, -int(math.log10(precision)))
        min_load = round(10**(-decimal_places),9)   # Start with the lowest load
        max_load = round(1.0 - min_load,9)          # End with the highest load
        load = min_load                             # Current load
        granularity = 0.1                           # Current granularity -> Will be reduced if saturation point is reached
        while True:
            saturation_reached = False
            # Export the BookSim configuration file
            export_booksim_config(inputs, run_identifier, load)
            # Run BookSim
            exec_identifier = "%s_load_%0.*f" % (run_identifier, decimal_places, load)
            result = execute_booksim(exec_path, config_path, time_limit, exec_identifier, "rapidchiplet/logs", inputs["verbose"])
            # We store the result of each run, also the not successful ones. It is up to the user to check the logs
            results[str(load)] = result
            # If the simulation was successful: Proceed with the next load
            if result["return_code"] == 0:
                # If the packet latency is missing -> Something went wrong. Abort the simulation
                if "packet_latency" not in result:
                    txt = ("ERROR: Packet latency missing in BookSim output for load %%.%df. " % decimal_places)
                    hlp.print(txt % load)
                    break
                # Check if saturation throughput has been reached
                elif (min_load in results) and ((results[min_load]["packet_latency"]["avg"] * saturation_factor) < results[load]["packet_latency"]["avg"]):
                    saturation_reached = True
            # We treat each unsuccessful run as saturation point reached
            # It is up to the user to check the logs and see why the run failed
            else:
                saturation_reached = True
            # If the saturation point has been reached go to finer granularity or abort
            if saturation_reached:
                # We already are at the maximum precision -> Terminate
                if granularity <= precision:
                    break
                # If we are at the minimum load but we already reached saturation -> Terminate
                elif load == min_load:
                    break
                # We can reduce granularity
                else:
                    load = round((load - granularity) + (granularity / 10),9)
                    granularity = round(granularity * 0.1,9)
            # Saturation point not reached yet
            elif load < max_load:
                if (load == min_load) and (granularity > precision):
                    load = round(granularity, 9)
                else:
                    load = round(load + granularity,9)
            # Network can support a load of 0.999 -> Terminate
            else:
                break
    elif booksim_config["mode"] == "trace":
        export_booksim_config(inputs, run_identifier, 1.0)
        result = execute_booksim(exec_path, config_path, time_limit, run_identifier, "rapidchiplet/logs", inputs["verbose"])
        results["trace"] = result
    else:
        hlp.print("ERROR: Unknown BookSim mode '%s' specified." % booksim_config["mode"])


    results = dict(sorted(results.items()))
    return results    
