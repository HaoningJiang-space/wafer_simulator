# Python modules
import sys
import re
import math
from typing import List, Dict, Set, Tuple
from collections import deque
from pyroaring import BitMap
import time
from collections import defaultdict

# Custom modules
import helpers as hlp
import config as cfg

def topo_numbers(dependencies: List[List[int]]) -> List[int]:
    """
    dependencies[a] = [b,c,...] means a depends on b,c,...  (edges b->a)
    returns order s.t. order[a] = topological index of node a
    """
    n = len(dependencies)
    graph = [[] for _ in range(n)]   # b -> [a,...]
    indeg = [0]*n

    for a, deps in enumerate(dependencies):
        for b in deps:
            graph[b].append(a)
            indeg[a] += 1

    q = deque([u for u in range(n) if indeg[u] == 0])
    order = [-1]*n
    i = 0
    while q:
        u = q.popleft()
        order[u] = i
        i += 1
        for v in graph[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)

    if i != n:
        print("ERROR: cycle detected in dependencies. i = %d, n = %d" % (i, n))
        raise ValueError("cycle detected in dependencies")
    return order


def topo_numbers_break_cycles(dependencies: List[List[int]]) -> Tuple[List[int], Set[Tuple[int,int]]]:
    """
    dependencies[a] = [b,c,...] means edge b->a.
    Returns:
        order[a] = topological index
        removed = set of removed edges (b,a) to break cycles.
    """

    n = len(dependencies)
    graph = [[] for _ in range(n)]
    indeg = [0]*n

    for a, deps in enumerate(dependencies):
        for b in deps:
            graph[b].append(a)
            indeg[a] += 1

    removed = set()
    order = [-1]*n
    i = 0
    q = deque([u for u in range(n) if indeg[u] == 0])
    remaining = set(range(n))

    while remaining:
        if not q:
            # cycle: pick arbitrary node r with indeg[r] > 0
            r = next(iter(remaining))
            # remove any incoming edge (b -> r)
            found = False
            for b in range(n):
                if r in graph[b]:
                    graph[b].remove(r)
                    indeg[r] -= 1
                    removed.add((b, r))
                    found = True
                    break
            if not found:
                raise RuntimeError("internal error: cannot find incoming edge to remove")
            if indeg[r] == 0:
                q.append(r)
            continue

        u = q.popleft()
        if u not in remaining:
            continue
        remaining.remove(u)
        order[u] = i
        i += 1
        for v in list(graph[u]):
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)

    return order, removed



def apply_removed_fast(dependencies, removed_deps):
    rm = defaultdict(set)
    for b, a in removed_deps:
        rm[a].add(b)

    out = []
    for a, deps in enumerate(dependencies):
        bad = rm.get(a)
        if not bad:
            out.append(deps[:])        # no removals for this a
        else:
            out.append([b for b in deps if b not in bad])
    return out


def convert_goal_trace_to_rapidchiplet_trace(path_goal_trace : str, path_rapidchiplet_trace : str) -> None:
    """
    Converts a goal trace file to a RapidChiplet trace file.

    Parameters:
    path_goal_trace (str): The file path to the input goal trace.
    path_rapidchiplet_trace (str): The file path to the output RapidChiplet trace.

    Notes:
    - In GOAL traces, cpu IDs and labels are per rank and not globally unique.
    """

    # Initialize instruction limit with a high value; will be updated when reading the trace
    instruction_limit_per_rank = 1000000000  # 1 billion instructions per rank
    num_ranks = None
    cur_rank = None
    gpu_per_rank = []

    # Format: this_rank -> other_rank -> tag -> (gpu, label_id, size)
    sends = []
    recvs = []

    # Format: (rank, label) -> label_id
    label_to_id = {}

    # Format: label_id -> type
    label_id_to_type = []

    # Format label_id -> list of dependencies (label_ids that his label depends on)
    dependencies = []

    # Format: label_id -> (source_chiplet_id, dest_chiplet_id, size_in_bytes) only for send labels
    label_id_to_msg_info = {}

    # label_id to runtime
    label_id_to_runtime = []

    hlp.print_cyan("Reading goal trace from %s" % path_goal_trace)
    start_time = time.time()
    with open(path_goal_trace, 'r') as goal_trace:
        # Manual loop
        while True:
            line = goal_trace.readline()
            if not line:
                break
            # Break after the instruction limit is reached
            m = re.match(r"^l(\d+)", line)
            if m and int(m.group(1)) >= instruction_limit_per_rank:
                continue
            parts = line.split()
            # Number of ranks at the top of the file
            if line.startswith("num_ranks"):
                num_ranks = int(parts[1])
                sends = [[{} for _ in range(num_ranks)] for _ in range(num_ranks)]
                recvs = [[{} for _ in range(num_ranks)] for _ in range(num_ranks)]
                gpu_per_rank = [0 for _ in range(num_ranks)]
                # TODO: Here we set the instruction limit per rank to aim at a certain overall instruction limit
                overall_instruction_limit = 1000000 # 1 million instructions overall
                instruction_limit_per_rank = overall_instruction_limit // num_ranks
            # Current rank indicator at the head of a rank's section
            elif line.startswith("rank"):
                cur_rank = int(parts[1])
                # Check that num_ranks is defined
                if num_ranks is None:
                    hlp.register_error("Number of ranks not defined before rank sections.")
                # Check that rank index is valid
                if cur_rank < 0 or cur_rank >= num_ranks:
                    hlp.register_error(f"Invalid rank index: %s for num_ranks: %s" % (cur_rank, num_ranks))
            # Calculation
            elif "calc" in line:
                # Read line | Syntax: <label>: calc <time> cpu <gpu-stream>
                label = parts[0][:-1]
                calc_time = int(parts[2]) # Time in ns, currently not used
                # Identify label ID
                if (cur_rank, label) in label_to_id:
                    label_id = label_to_id[(cur_rank, label)]
                else:
                    label_id = len(label_to_id)
                    label_to_id[(cur_rank,label)] = label_id
                # Store label type
                while len(label_id_to_type) <= label_id:
                    label_id_to_type.append(None)
                label_id_to_type[label_id] = "calc"
                # Store runtime info
                while len(label_id_to_runtime) <= label_id:
                    label_id_to_runtime.append(0)
                label_id_to_runtime[label_id] = calc_time
            # Send operation
            elif "send" in line:
                # Read line | Syntax: <label>: send <size> to <dest_rank> tag <tag> cpu <gpu-stream> nic <gpu>
                label = parts[0][:-1]
                size = int(parts[2][:-1])  # Size in Bytes; Remove trailing "b"
                dest_rank = int(parts[4])
                tag = int(parts[6])
                gpu = int(parts[10])
                # Idenfity label ID
                if (cur_rank, label) in label_to_id:
                    label_id = label_to_id[(cur_rank, label)]
                else:
                    label_id = len(label_to_id)
                    label_to_id[(cur_rank,label)] = label_id
                # Store send operation
                if tag not in sends[cur_rank][dest_rank]:
                    sends[cur_rank][dest_rank][tag] = []
                sends[cur_rank][dest_rank][tag].append((gpu, label_id, size))
                # Update number of GPUs for this rank
                gpu_per_rank[cur_rank] = max(gpu_per_rank[cur_rank], gpu + 1)
                # Store label type
                while len(label_id_to_type) <= label_id:
                    label_id_to_type.append(None)
                label_id_to_type[label_id] = "send"
                # Store runtime info
                while len(label_id_to_runtime) <= label_id:
                    label_id_to_runtime.append(0)
                label_id_to_runtime[label_id] = 0  # Send time not modeled 
            # Receive operation
            elif "recv" in line:
                # Read line | Syntax: <label>: recv <size> from <src_rank> tag <tag> cpu <gpu-stream> nic <gpu> # 
                label = parts[0][:-1]
                size = int(parts[2][:-1])  # Remove trailing "b"; Size in Bytes
                src_rank = int(parts[4])
                tag = int(parts[6])
                gpu = int(parts[10])
                # Idenfity label ID
                if (cur_rank, label) in label_to_id:
                    label_id = label_to_id[(cur_rank, label)]
                else:
                    label_id = len(label_to_id)
                    label_to_id[(cur_rank,label)] = label_id
                # Store recv operation
                if tag not in recvs[cur_rank][src_rank]:
                    recvs[cur_rank][src_rank][tag] = []
                recvs[cur_rank][src_rank][tag].append((gpu, label_id, size))
                # Update number of GPUs for this rank
                gpu_per_rank[cur_rank] = max(gpu_per_rank[cur_rank], gpu + 1)
                # Store label type
                while len(label_id_to_type) <= label_id:
                    label_id_to_type.append(None)
                label_id_to_type[label_id] = "recv"
                # Store runtime info
                while len(label_id_to_runtime) <= label_id:
                    label_id_to_runtime.append(0)
                label_id_to_runtime[label_id] = 0  # Recv time not modeled
            # Dependencies
            elif "requires" in line:
                # Read line | Syntax: <label1> requires <label2> # label2 must be compte before label1 can start
                label1 = parts[0]
                label2 = parts[2]
                # Check if label2 exceeds instruction limit, if yes, skip dependency
                m = re.match(r"^l(\d+)", label2)
                if m and int(m.group(1)) >= instruction_limit_per_rank:
                    continue
                # Identify label IDs
                if (cur_rank, label1) in label_to_id:
                    label_id_1 = label_to_id[(cur_rank, label1)]
                else:
                    label_id_1 = len(label_to_id)
                    label_to_id[(cur_rank,label1)] = label_id_1
                if (cur_rank, label2) in label_to_id:
                    label_id_2 = label_to_id[(cur_rank, label2)]
                else:
                    label_id_2 = len(label_to_id)
                    label_to_id[(cur_rank,label2)] = label_id_2
                # Store dependency
                while len(dependencies) <= max(label_id_1, label_id_2):
                    dependencies.append([])
                dependencies[label_id_1].append(label_id_2)
            # End of rank section -> skip
            elif line == "}\n":
                continue
            # Empty line -> skip
            elif line == "\n":
                continue
            # Unknown line type
            else:
                print(f"Unknown line type: \"%s\"" % line)
    print("INFO: Goal trace read in %.2f seconds" % (time.time() - start_time))

    # Map (rank, gpu) tuple to global Chiplet ID
    hlp.print_cyan("Mapping (rank, gpu) to global Chiplet ID")
    start_time = time.time()
    chiplet_id_map = {}
    next_chiplet_id = 0
    for rank in range(num_ranks):
        print("INFO: Rank %s has %s GPUs" % (rank, gpu_per_rank[rank]))
        for gpu in range(gpu_per_rank[rank]):
            chiplet_id_map[(rank, gpu)] = next_chiplet_id
            next_chiplet_id += 1
    print("INFO: Chiplet ID map generated in %.2f seconds" % (time.time() - start_time))

    # Match sends and recvs by tags and add dependencies between them
    hlp.print_cyan("Matching sends and recvs and adding dependencies")
    start_time = time.time()

    intra_rank_messages = 0
    inter_rank_messages = 0
    total_messages = 0

    sends_not_matched = 0
    sends_multiple_matched = 0
    sends_size_mismatch = 0

    for s_rank in range(num_ranks):
        for r_rank in range(num_ranks):
            for s_tag in sends[s_rank][r_rank]:
                for (s_gpu, s_label_id, s_size) in sends[s_rank][r_rank][s_tag]:
                    # Idenfity the corresponding recv
                    candidates = recvs[r_rank][s_rank].get(s_tag, [])
                    if len(candidates) == 0:
                        sends_not_matched += 1
                    elif len(candidates) == 1:
                        (r_gpu, r_label_id, r_size) = candidates[0]
                        # Check if sizes matches
                        if s_size == r_size:
                            total_messages += 1
                            if s_rank == r_rank:
                                intra_rank_messages += 1
                            else:
                                inter_rank_messages += 1
                            # Add dependency: send must complete before recv can start
                            while len(dependencies) <= max(s_label_id, r_label_id):
                                dependencies.append([])
                            dependencies[r_label_id].append(s_label_id)
                            # Store message info
                            label_id_to_msg_info[s_label_id] = (chiplet_id_map[(s_rank, s_gpu)], chiplet_id_map[(r_rank, r_gpu)], s_size)
                        else:
                            sends_size_mismatch += 1
                    elif len(candidates) > 1:
                        sends_multiple_matched += 1
    print("INFO: Sends and recvs matched and dependencies added in %.2f seconds" % (time.time() - start_time))
    print("INFO: Total intra-rank messages: %s" % intra_rank_messages)
    print("INFO: Total inter-rank messages: %s" % inter_rank_messages)
    print("INFO: Total messages: %s" % total_messages)
    print("INFO: Sends not matched (likely due to message limit - ignoring): %s" % sends_not_matched)
    print("INFO: Sends with multiple recvs matched (likely due to message limit - ignoring): %s" % sends_multiple_matched)
    print("INFO: Sends and recvs size mismatch (likely due to message limit - ignoring): %s" % sends_size_mismatch)

    # Computing topological order and order label_ids accordingly. Also detect and break cycles if any.
    hlp.print_cyan("Computing topological order")
    start_time = time.time()
    order, removed_deps = topo_numbers_break_cycles(dependencies)
    print("INFO: Topological order computed in %.2f seconds" % (time.time() - start_time))

    # Remove the dependencies that were removed to break cycles
    hlp.print_cyan("Removing dependencies that were removed to break cycles")
    start_time = time.time()
    dependencies = apply_removed_fast(dependencies, removed_deps)
    print("INFO: Cyclic dependencies removed in %.2f seconds" % (time.time() - start_time))
    print("INFO: Number of removed dependencies to break cycles: %s" % len(removed_deps))

    # Compute reverse dependencies
    hlp.print_cyan("Computing reverse dependencies")
    start_time = time.time()
    reverse_dependencies = [[] for _ in range(len(dependencies))]
    for i in range(len(dependencies)):
        for dep_idx in dependencies[i]:
            reverse_dependencies[dep_idx].append(i)
    print("INFO: Reverse dependencies computed in %.2f seconds" % (time.time() - start_time))

    # Creating messages in the RapidChiplet format
    hlp.print_cyan("Generating messages between chiplets, including dependencies")
    start_time = time.time()
    instructions = []
    flit_size_in_bytes = cfg.link_bandwidth_bit_per_sec / cfg.network_frequency_hz / 8
    per_chiplet_cycle = {}
    # Iterate through label IDs in topological order
    for label_id in sorted(range(len(label_id_to_type)), key=lambda x: order[x]):
        label_type = label_id_to_type[label_id]
        # Only send labels correspond to real messages, others are only used for dependencies
        # Only add the message if the send was matched to a recv
        if label_type == "send" and label_id in label_id_to_msg_info:
            (src_chiplet_id, dst_chiplet_id, size_in_bytes) = label_id_to_msg_info[label_id]
            if src_chiplet_id not in per_chiplet_cycle:
                per_chiplet_cycle[src_chiplet_id] = 0
            # Cycles are only for ordering messages, actual compute time is not modeled yet, could be added later if needed
            cycle = per_chiplet_cycle[src_chiplet_id]
            per_chiplet_cycle[src_chiplet_id] += 1
            ignore = False
        else:
            cycle = 0
            ignore = True
            src_chiplet_id = -1
            dst_chiplet_id = -1
            size_in_bytes = 0
        # Construct the message entry
        msg = {}
        msg["id"] = order[label_id]
        msg["cycle"] = cycle
        msg["src"] = src_chiplet_id
        msg["dst"] = dst_chiplet_id
        msg["num_flits"] = int(math.ceil(size_in_bytes / flit_size_in_bytes))
        msg["rev_deps"] = [order[x] for x in reverse_dependencies[label_id]]
        msg["num_deps"] = len(dependencies[label_id])
        msg["duration"] = label_id_to_runtime[label_id]
        msg["ignore"] = ignore
        instructions.append(msg)
    print("INFO: Instructions generated in %.2f seconds" % (time.time() - start_time))
    print("INFO: Total number of instructions: %s" % len(instructions))

    # Store the RapidChiplet trace
    hlp.print_cyan("Writing RapidChiplet trace to %s" % path_rapidchiplet_trace)
    hlp.write_json(path_rapidchiplet_trace, instructions)

if __name__ == "__main__":
    if len(hlp.sys.argv) != 3:
        hlp.register_error("Usage: python convert_goal_trace_to_rapidchiplet_trace.py <path_goal_trace> <path_rapidchiplet_trace>")
    path_goal_trace = hlp.sys.argv[1]
    path_rapidchiplet_trace = hlp.sys.argv[2]
    convert_goal_trace_to_rapidchiplet_trace(path_goal_trace, path_rapidchiplet_trace)
