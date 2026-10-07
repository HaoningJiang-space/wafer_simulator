# Python modules
from typing import Tuple, Dict, List
from collections import deque
import random
import numpy as np
import pymetis

# Custom modules
import helpers as hlp
from System import System

def add_global_reticle_ids(system: System) -> None:
    """ Add a global reticle ID to each reticle in the system.
    Args:
        system (System): The system containing wafers and reticles.
    Returns:
        None
    """
    global_id = 0
    for wafer in system.wafers:
        for reticle in wafer.reticles:
            reticle.attributes["global_reticle_id"] = global_id
            global_id += 1
    return None

def add_neighbor_information(system: System) -> List[int]:
    """ Add neighbor information to each reticle in the system.
    Args:
        system (System): The system containing wafers and reticles.
    Returns:
        None
    """
    # Add the "neighbors" attribute to each reticle in the system.
    for wafer in system.wafers:
        for reticle in wafer.reticles:
            reticle.attributes["neighbors"] = []
    # Iterate through wafers
    for (wid, wafer) in enumerate(system.wafers):
        # Iterate through reticles
        for (rid, reticle) in enumerate(wafer.reticles):
            # Check connectivity to the wafer below if it exists
            # The wafer above is not checked since once the wafer above will be processed, it will insert the links 
            if wid > 0:
                owid = wid - 1
                other_wafer = system.wafers[owid]
                # Iterate through reticles in the other wafer
                for (orid, other_reticle) in enumerate(other_wafer.reticles):
                    # Iterate through vertical connectors in the current reticle
                    for (vcid, vc) in enumerate(reticle.vertical_connectors):
                        # Iterate through vertical connectors in the other reticle
                        for (ovcid, ovc) in enumerate(other_reticle.vertical_connectors):
                            # Check if the vertical connections overlap
                            if vc.overlaps(ovc):
                                reticle.attributes["neighbors"].append((owid, orid, ovcid, vcid))
                                other_reticle.attributes["neighbors"].append((wid, rid, vcid, ovcid))
    # Add the number of neighbors to each reticle as a separate attribute and collect statistics
    all_neighbor_counts = []
    for wafer in system.wafers:
        for reticle in wafer.reticles:
            reticle.attributes["n_neighbors"] = len(set((wid, rid) for (wid, rid, vcid, _) in reticle.attributes["neighbors"]))
            all_neighbor_counts.append(reticle.attributes["n_neighbors"])
    return all_neighbor_counts

def add_path_lenths(system: System) -> List[int]:
    """ Compute the path lengths between all pairs of compute reticles.
    Args:
        adj_List (List[List[int]]): The adjacency List of the graph.
    Returns:
        List[int]: A list of path lengths for each pair of nodes.
    """
    # Check that the system has neighbor information
    if not all("neighbors" in reticle.attributes for wafer in system.wafers for reticle in wafer.reticles):
        hlp.register_error("Missing neighbor information in reticles. Please run add_neighbor_information(system) first.")
    # Track and return all path lengths for easy computation of diameter and average path length
    all_path_lengths = []
    # Iterate through all reticles and compute the path lengths
    for (wid, wafer) in enumerate(system.wafers):
        for (rid, reticle) in enumerate(wafer.reticles):
            if reticle.typ == "compute":
                # initialize data structures for BFS
                visited = {(wid_, rid_): False for wid_ in range(len(system.wafers)) for rid_ in range(len(system.wafers[wid_].reticles))}
                path_lengths = {(wid_, rid_) : float("inf") for wid_ in range(len(system.wafers)) for rid_ in range(len(system.wafers[wid_].reticles))}
                # Start at current reticle
                queue = deque([(wid, rid)])
                visited[(wid, rid)] = True
                path_lengths[(wid, rid)] = 0
                # BFS to compute path lengths
                while queue:
                    (cwid,crid) = queue.popleft()
                    for (owid, orid, ovcid, _) in system.wafers[cwid].reticles[crid].attributes["neighbors"]:
                        if not visited[(owid, orid)]:
                            visited[(owid, orid)] = True
                            path_lengths[(owid, orid)] = path_lengths[(cwid, crid)] + 1
                            queue.append((owid, orid))
                # Store the path lengths in the reticle attributes
                path_lengths_compute_only = {(wid_, rid_) : length for (wid_, rid_), length in path_lengths.items() if system.wafers[wid_].reticles[rid_].typ == "compute"}
                reticle.attributes["path_lengths"] = path_lengths_compute_only
                reticle.attributes["avg_path_length"] = float(np.mean(list(path_lengths_compute_only.values())))
                all_path_lengths.extend(path_lengths_compute_only.values())
    return all_path_lengths

def extract_adjacency_list(system: System) -> List[List[int]]:
    """
    Extract the adjacency list from the system.
    Args:
        system (System): The system containing wafers and reticles.
    Returns:
        List[List[int]]: The adjacency list of the graph.
    """
    # Check that the system has neighbor information
    if not all("neighbors" in reticle.attributes for wafer in system.wafers for reticle in wafer.reticles):
        hlp.register_error("Missing neighbor information in reticles. Please run add_neighbor_information(system) first.")
    adj_List = []
    reticle_id_map = {}
    # Create a mapping from reticle to its index
    for (wid, wafer) in enumerate(system.wafers):
        for (rid, reticle) in enumerate(wafer.reticles):
            reticle_id_map[(wid, rid)] = len(adj_List)
            adj_List.append([])
    # Build the adjacency list
    for (wid, wafer) in enumerate(system.wafers):
        for (rid, reticle) in enumerate(wafer.reticles):
            current_index = reticle_id_map[(wid, rid)]
            # Iterate through neighbors and add edges to the adjacency list
            for (owid, orid, ovcid, _) in reticle.attributes["neighbors"]:
                neighbor_index = reticle_id_map[(owid, orid)]
                adj_List[current_index].append(neighbor_index)
                # Since the graph is undirected, add the reverse edge as well
                adj_List[neighbor_index].append(current_index)
    # Return the adjacency list
    return adj_List 

def estimate_bisection_bandwidth(adj_List: List[List[int]], reps: int = 10) -> Tuple[float, float]:
    """
    Estimate the bisection bandwidth of the graph using the PyMetis library.
    Args:
        adj_List (List[List[int]]): The adjacency List of the graph.
        reps (int): The number of repetitions for the estimation.
    Returns:
        Tuple[float, float]: The mean and standard deviation of the estimated bisection bandwidth
    """
    n = len(adj_List)
    cuts = []
    for _ in range(reps):
        seed = random.randint(0, 1 << 30)
        opts = pymetis.Options(seed=seed)
        _, parts = pymetis.part_graph(2, adjacency=adj_List, options=opts)
        cut_edges = sum(1 for u in range(n) for v in adj_List[u] if parts[u] != parts[v]) // 2
        cuts.append(cut_edges)
    return (float(np.mean(cuts)), float(np.std(cuts)))


def analyze_topology(system: System):
    """
    Analyze the topology of the system and print the results.
    Args:
        system (System): The system to analyze.
    """


    # Add neighbor and path length information to the system
    neighbor_counts = add_neighbor_information(system)
    path_lengths = add_path_lenths(system)
    adj_List = extract_adjacency_list(system)
    bisection_bandwidth = estimate_bisection_bandwidth(adj_List)

    results = {}
    # General information
    results["n_wafers"] = len(system.wafers)
    results["n_reticles"] = len([ret for wafer in system.wafers for ret in wafer.reticles])
    results["n_compute_reticles"] = len([ret for wafer in system.wafers for ret in wafer.reticles if ret.typ == "compute"])
    results["n_interconnect_reticles"] = len([ret for wafer in system.wafers for ret in wafer.reticles if ret.typ == "interconnect"])
    # Topology information
    results["diameter"] = max(path_lengths) 
    results["neighbor_counts"] = neighbor_counts
    results["neighbor_count_mean"] = float(np.mean(neighbor_counts))
    results["neighbor_count_std"] = float(np.std(neighbor_counts))
    results["path_lengths"] = path_lengths
    results["path_length_mean"] = float(np.mean([length for length in path_lengths if length != -1]))
    results["path_length_std"] = float(np.std([length for length in path_lengths if length != -1]))
    results["bisection_bandwidth_mean"] = bisection_bandwidth[0]
    results["bisection_bandwidth_std"] = bisection_bandwidth[1]
    # Return the results
    return results

