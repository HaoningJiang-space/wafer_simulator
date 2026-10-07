# Import python libraries
import networkx as nx
import itertools as it
import argparse
import random
import queue
import sys

# Import RapidChiplet files
from . import helpers as hlp
from . import routing_utils as utils

#########################################################################################################
# Routing algorithms
#########################################################################################################

# The fact that we always use the shortest path with the lowest next-hop-id results in deterministic,
# deadlock-free routing. However, the path diversity is not exploited, and congestion may occur.
# Consider all chiplets as lower-id than all interposer-routers.
def shortest_path_lowest_id_first_routing(adj_list):    
    n = len(adj_list)
    # Output: One routing table for each node.
    routing_table = {cur : {dst : None for dst in range(n)} for cur in range(n)}
    # Run Dijkstra's algorithm.
    for dst in range(n):
        dists = {src : float("inf") for src in range(n)}
        nexts = {src : None for src in range(n)}
        todo = queue.PriorityQueue()    
        # Start from the destination
        dists[dst] = 0
        todo.put((0, dst))
        # Explore the graph
        while not todo.empty():
            (cur_dist, cur) = todo.get()
            # Skip if we have already found a shorter path to the current node
            if cur_dist > dists[cur]:
                continue
            # Iterate over neighbors of the current node
            for nei in adj_list[cur]:
                nei_dist = cur_dist + 1
                # If we found a shorter path from the neighbor to the destination
                # or a path of equal length but with a lower id
                if (nei_dist < dists[nei]) or ((nei_dist == dists[nei]) and (nexts[nei] > cur)):
                    dists[nei] = nei_dist
                    nexts[nei] = cur
                    todo.put((nei_dist, nei))
        # Verify that all nodes have a valid path to the destination and construct the routing table
        for cur in range(n):
            if cur != dst:
                if nexts[cur] is None:
                    print("ERROR: Unable to find a path from node %s to node %s" % (str(cur), str(dst)))
                else:
                    routing_table[cur][dst] = nexts[cur]
    return {"type" : "default", "table" : routing_table}

# TODO: Currently not working - adapt go new and simplified adj_list format
def shortest_path_turn_model_random(ici_graph):
    # Create a directed graph for the shortest path computations
    G = nx.DiGraph()
    #also create undirected graph containing only the vertices with forwarding capacity to compute the forbidden turns set on.
    G_SCB = nx.Graph()

    # contains list of non forwarding chiplets
    non_forwarding = []
    # contains list of chiplets
    chiplets = []
    # contains list of all nodes in network
    nodes = []

    #The following 3 for-loops are used to fill up the graphs and lists defined above
    num_vertices= len(ici_graph['nodes'])
    for i in ici_graph['nodes']:
        nodes.append(i)
        G.add_node(i)
        # SCB only considers the forwarding routers
        if i[0] == 'irouter':
            G_SCB.add_node(i)
        else:
            chiplets.append(i)

    #add src and sink
    src = ('',num_vertices)
    sink = ('',num_vertices+1)

    #  add connections to from src sink for chiplet nodes.
    for i in ici_graph['relay_map'].keys():
        G.add_edge(src,i)
        G.add_edge(i, sink)
        if ici_graph['relay_map'][i] == True:
            G_SCB.add_node(i)
        else:
            non_forwarding.append(i)

    #add edges from adj list:
    for i in ici_graph['adj_list'].keys():
        for j in ici_graph['adj_list'][i]:
            G.add_edge(i, j)
            G.add_edge(j, i)
            if i in G_SCB.nodes() and j in G_SCB.nodes():
                G_SCB.add_edge(i,j)

    #compute the cycle breaking set for G_SCB
    forbidden_turns = []
    utils.simple_cycle_breaking(G_SCB, forbidden_turns)
    #generate the linegraph 
    LG =utils.generate_line_graph(G)

    #now remove forbidden turns and turns around non forwarding vertices
    to_remove = []
    for (e1,e2) in LG.edges:
        if (e1,e2) in forbidden_turns or (e1[1] in non_forwarding and e1[0] != src and e2[1] != sink ):
            to_remove.append((e1,e2))

    LG.remove_edges_from(to_remove)

    #now compute shortest paths from to all chiplets
    pred_map= {}
    utils.get_shortest_valid_paths(LG, chiplets, src, pred_map)

    #now compute the routing table

    #just so the neighbors are correct again
    G.remove_node(src)
    G.remove_node(sink)

    #routing table format is: routing_table[source][destination][previous] -> next_hop
    # notably:
    #   - no routing table entry to route from node i to node i.
    #   - when packets are injected into the network, they have prev = -1 
    routing_table = {node : {dst : {} for dst in [c for c in chiplets if c != node]} for node in nodes}

    for u in chiplets:
        for v in chiplets:
            # first clause covers the case, when there is no path from u to v in the network (as then we have no RT entry)
            if u == v or (v,sink) not in pred_map[u].keys():
                pass
            # if there is a path, we use the pred_map as a reverse_pred map and set the next hops until we arrive at u or 
            # until we find an entry in the routing table for the rest of the path.
            else:
                goal = (src,u)
                curr = (v,sink)
                # wait until we reach u
                while curr[0] != goal[1]:
                    next = random.choice(pred_map[u][curr])
                    first = curr[1]
                    second = curr[0]
                    third = next[0]
                    if first ==sink:
                        routing_table[second][u][-1] = third
                    else:
                        if first not in routing_table[second][u].keys():
                            routing_table[second][u][first] = third
                        else:
                            # or if routing table already contains an entry, rest of path is already fixed.
                            break
                    curr = next
    return {"type" : "extended", "table" : routing_table}

def generate_routing(chiplets, placement, topology, routing_algorithm):
    # Construct ICI graph
    ici_graph = hlp.construct_ici_graph(chiplets, placement, topology)
    # Construct routing table
    if routing_algorithm == "splif":
        routing_table = shortest_path_lowest_id_first_routing(ici_graph)
    elif routing_algorithm == "sptmr":
        routing_table = shortest_path_turn_model_random(ici_graph)
    else:
        print("ERROR: Unknown routing algorithm: %s" % routing_algorithm)
        sys.exit(1)
    # Store results
    return routing_table

if __name__ == "__main__":
    # Read command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-df", "--design_file", required = True, help = "Path to the \"design\" input file")
    parser.add_argument("-rtf", "--routing_table_file", required = True, help = "Name of the routing table file (is stored in ./inputs/routing_tables)")
    parser.add_argument("-ra", "--routing_algorithm", required = True, help = "Routing algorithm to use. Options: splif")
    args = parser.parse_args()
    # Read input files
    design = hlp.read_json(filename = args.design_file)
    chiplets = hlp.read_json(filename = design["chiplets"])
    placement = hlp.read_json(filename = design["placement"])
    topology = hlp.read_json(filename = design["topology"])
    # Generate routing table
    routing_table = generate_routing(chiplets, placement, topology, args.routing_algorithm)
    # Write routing
    hlp.write_json("./inputs/routing_tables/%s.json" % args.routing_table_file, routing_table)

