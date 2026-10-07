#include "simple_cycle_breaking_set_routing.hpp"
#include <vector>
#include <tuple>
#include <map>
#include <set>
#include <climits>
#include <iostream>
#include <algorithm>
#include <cassert>


// Deadlock-free: YES
// Minimal: YES
// Deterministic: NO (possibly multiple output ports can be returned)
// Description: Shortest path routing that uses the simple cycle-breaking set strategy to achieve deadlock-freedom.
// Settings: Shortest paths w.r.t. hops vs. shortest paths w.r.t. latency
std::vector<std::tuple<int,int,int>> simple_cycle_breaking_set_routing::route(std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>> router_list, int n_routers, int n_nodes, int n_vsc, int cur_rid, int dst_nid, int in_port, int flit_id) const {
	// Vector to store all valid next hops (output port, min VC, max VC)
	std::vector<std::tuple<int,int,int>> valid_next_hops;
	// Identify input ports that are connected to nodes
	std::vector<int> node_input_ports;
	// Previous router id that is needed to access the routing table with turn restrictions
	int prev_rid;
	for (std::map<int,std::tuple<int,int,int>>::iterator it = router_list[0][cur_rid].begin(); it != router_list[0][cur_rid].end(); ++it) {
		node_input_ports.push_back(std::get<1>(it->second));
	}
	// Identify the previous router based on the input port for and use -1 if the packet has been injected at the current router
	if (std::find(node_input_ports.begin(), node_input_ports.end(), in_port) != node_input_ports.end()) {
		// Packet has been injected at the current router (no previous router)
		prev_rid = -1;
	} else {
		// Check that the previous router map is available; if not, compute it
		if (prev_router_map.find(cur_rid) == prev_router_map.end() or prev_router_map.at(cur_rid).find(in_port) == prev_router_map.at(cur_rid).end()) {
			compute_prev_router_map(router_list, n_routers);
		} 
		prev_rid = prev_router_map.at(cur_rid).at(in_port);
	}
	// If the routing table has not been precomputed for the current router, then compute it
	if (routing_table.find(prev_rid) == routing_table.end() or routing_table.at(prev_rid).find(cur_rid) == routing_table.at(prev_rid).end() or routing_table.at(prev_rid).at(cur_rid).find(dst_nid) == routing_table.at(prev_rid).at(cur_rid).end()) {
		for (int rid = 0; rid < n_routers; ++rid) {
			route_from_source(router_list, n_routers, n_nodes, rid);
		}
	}
	// Read the output ports from the routing table
	std::vector<int> out_ports = routing_table[prev_rid][cur_rid][dst_nid];
	// Sanity check: if no output ports are found, return an empty vector
	if (out_ports.empty()){
		std::cout << "Error: No output ports found for routing from router " << cur_rid << " to node " << dst_nid << " when coming from router " << prev_rid << " through port " << in_port << ". Returning no valid next hops." << std::endl;
		assert(false);
	}
	// Return all valid next hops (all VCs on the selected output ports)
	for (int out_port : out_ports){
		valid_next_hops.push_back(std::make_tuple(out_port, 0, n_vsc-1));
	}
	return valid_next_hops;
}


// Only sets the routing table entries of the current source router (cur_rid)
void simple_cycle_breaking_set_routing::route_from_source(std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>> router_list, int n_routers, int n_nodes, int src_rid) const {
	// TODO: Hard-coded distance metric: true = latency, false = hops
	bool use_latency_for_distance = false;
	// Check that the simple cycle-breaking set has been computed; if not, compute it
	if (permitted_turns.empty() && forbidden_turns.empty()) {
		compute_permitted_turns(router_list, n_routers);
	}
	// Data structures for Dijkstra's algorithm
	// We use multiple possible previous routers to allow for multiple equal-cost paths
	std::vector<int> dist(n_routers, INT_MAX);
	std::vector<std::vector<int>> prevs(n_routers, std::vector<int>());
	std::set<int> todo;
	// Auxiliary variables (allocate only once)
	int link_latency;
	int nei_rid;
	int new_distance;
	int nid;
	int port;
	int cur_rid;
	int prev_rid;
	int n_src_reached;
	int n_src_not_reached;	
	bool has_vali_turn;
	bool last_hop;
	bool is_permitted_turn;
	// Initialize the source router
	dist[src_rid] = 0;
	todo.insert(src_rid);
	// Dijkstra's algorithm main loop
	while (!todo.empty()) {
		// Find the router with the smallest distance (and lowest ID in case of ties)
		cur_rid = -1;
		for (int rid : todo) {
			if (cur_rid == -1 || dist[rid] < dist[cur_rid] || (dist[rid] == dist[cur_rid] && rid < cur_rid)) {
				cur_rid = rid;
			}
		}
		todo.erase(cur_rid);
		// Explore neighbors of the current router
		for (std::map<int,std::tuple<int,int,int>>::iterator it = router_list[1][cur_rid].begin(); it != router_list[1][cur_rid].end(); ++it) {
			nei_rid = it->first;	
			// Only explore neighbors that are reachable via a permitted turns. This is the main modification to Dijkstra's algorithm to implement the simple cycle-breaking set strategy
			has_vali_turn = false;
			for (int prev : prevs[cur_rid]) {
				if (std::find(permitted_turns.begin(), permitted_turns.end(), std::make_tuple(prev, cur_rid, nei_rid)) != permitted_turns.end()) {
					has_vali_turn = true;
					break;
				}
			}
			if (prevs[cur_rid].empty() || has_vali_turn) {
				link_latency = std::get<2>(it->second);
				new_distance = dist[cur_rid] + (use_latency_for_distance ? link_latency : 1);
				// New shorter path found
				if (new_distance < dist[nei_rid]) {
					dist[nei_rid] = new_distance;
					prevs[nei_rid].clear();
					prevs[nei_rid].push_back(cur_rid);
					todo.insert(nei_rid);
				// Another equal-cost path found
				} else if (new_distance == dist[nei_rid]) {
					prevs[nei_rid].push_back(cur_rid);
				}
			}
		}
	}
	// Use back-tracking to set the routing table entries for all nodes in the network
	for (int dst_rid = 0; dst_rid < n_routers; ++dst_rid) {
		// Here, we configure the routing for packets that have already reached their destination router and need to be ejected to the correct node
		if (dst_rid == src_rid) {
			// Add the correct output port for all local nodes
			for (std::map<int,std::tuple<int,int,int>>::iterator it = router_list[0][src_rid].begin(); it != router_list[0][src_rid].end(); ++it) {
				nid = it->first;		
				port = std::get<0>(it->second);
				// This needs to be added for all possible previous routers
				// No checking of turn is needed here as the last hop is a node and hence does not create a cycle
				// We need to consider all possible previous routers as the packet could have arrived from any direction (for this case, the above Dijkstra does not contain any previous router information)
				for (std::map<int, int>::iterator it = prev_router_map[src_rid].begin(); it != prev_router_map[src_rid].end(); ++it)
				{
					prev_rid = it->second;
					routing_table[prev_rid][src_rid][nid] = {port};
				}
				// In addition, add the entry for prev_rid = -1 (injected at the source router which is also the destination router)
				routing_table[-1][src_rid][nid] = {port};
			}
		// Other routers:
		} else {
			// Back-track to find the next hop and set the output port accordingly
			// Instead of a single intermediate hop, we need to keep tack of multiple possible intermediate hops (due to multiple equal-cost paths)
			// In addition, instead of a single router-id per hop, we need to keep track of (cur,next) pairs to be able to check for permitted turns
			std::vector<std::pair<int,int>> intermediate_hops;
			intermediate_hops.push_back({dst_rid,-1});
			// We use a while-true loop and break it when the source is reached (i.e. for all hop in intermediate_hops, hop.first is the source router)
			while (true) {
				// Check if we have reached the source router and need to stop back-tracking
				n_src_reached = 0;
				n_src_not_reached = 0;	
				for (std::pair<int,int> hop : intermediate_hops) {
					// This is the last intermediate hop; it has only one previous router (the source router)
					if (hop.first == src_rid) {
						n_src_reached++;	
					// This is not the last intermediate hop; the source router is not among the previous routers
					} else {
						n_src_not_reached++;
					}
				}
				// All paths reached the source router -> stop back-tracking
				if (n_src_reached > 0 && n_src_not_reached == 0) {
					break;
				// All paths have not yet reached the source router -> continue back-tracking
				} else if (n_src_reached == 0 && n_src_not_reached > 0) {
					// For all intermediate hops (i.e. paths that are explored in parallel), transition one hop towards the source router; Only keep ones that use permitted turns
					std::vector<std::pair<int,int>> new_intermediate_hops;
					for (std::pair<int,int> hop : intermediate_hops) {
						// Sanity check: Is there at least one previous router for the current hop? This part of the code is only executed if hop.first != src_rid
						if (prevs[hop.first].empty()) {
							std::cout << "Error: No previous routers exist when back-tracking from router " << dst_rid << " to source router " << src_rid << " at intermediate router " << hop.first << ". This indicates that no path exists." << std::endl;
							assert(false);
						}
						// Explore all previous routers for the current hop
						for (int prev : prevs[hop.first]) {
							// Check if this is the last hop (i.e., cur_rid is the destination router and hence, there is no turn and we can always keep this path)
							last_hop = (hop.first == dst_rid && hop.second == -1);
							// Check if this is a permitted turn. For the last hop, this reports false
							is_permitted_turn = (std::find(permitted_turns.begin(), permitted_turns.end(), std::make_tuple(prev, hop.first, hop.second)) != permitted_turns.end());
							// Add the routing information for this hop to the routing table (nothing to add for the last hop, ejection of packets is handled separately)
							if (not last_hop && is_permitted_turn){
								// Identify the output port at cur_rid to reach next_rid
								port = std::get<0>(router_list[1][hop.first][hop.second]);
								// We need to configure this for all possible nodes attached to the destination router
								for (std::map<int,std::tuple<int,int,int>>::iterator it = router_list[0][dst_rid].begin(); it != router_list[0][dst_rid].end(); ++it) {
									nid = it->first;
									// Avoid duplicates
									if (std::find(routing_table[prev][hop.first][nid].begin(), routing_table[prev][hop.first][nid].end(), port) == routing_table[prev][hop.first][nid].end()) {
										routing_table[prev][hop.first][nid].push_back(port);
									}
								}
							}
							// Continue back-tracking by adding (prev, cur) to the new intermediate hops. This also needs to be done for the last hop
							if (last_hop || is_permitted_turn) {
								// Do not add any duplicates to the list of new intermediate hops; This means that dst->src paths can converge (i.e., src->dst paths can diverge)
								if (std::find(new_intermediate_hops.begin(), new_intermediate_hops.end(), std::make_pair(prev, hop.first)) == new_intermediate_hops.end()) {

									new_intermediate_hops.push_back({prev, hop.first});
								}
							}
						}
					}
					// Update the intermediate hops for the next iteration
					intermediate_hops = new_intermediate_hops;
				// Error: Some paths reached the source router while others have not -> this should not happen in equal-cost path routing
				} else if (n_src_reached > 0 && n_src_not_reached > 0) {
					std::cout << "Error: Some paths reached the source router while others have not when back-tracking from router " << dst_rid << " to source router " << src_rid << ". This indicates an inconsistency in the path." << std::endl;
					assert(false);
				// Error: No paths exist (this should not happen)
				} else {
					std::cout << "Error: No paths exist when back-tracking from router " << dst_rid << " to source router " << src_rid << ". This indicates that no path exists." << std::endl;
					assert(false);
				}
			}
			// Post-condition of the previous loop: The intermediate_hops vector contains all (cur,next) pairs with cur being the source router
			// For packets injected at src_rid, all routign tables are set except the ones at src_rid
			// For packets arriving at src_rid from a different router, all routing table entries will be set by the corresponding call to route_from_source with that router as source
			// All we have to do is to set the routing table entries at src_rid for packets injected at src_rid
			for (std::pair<int,int> hop : intermediate_hops) {
				int nxt_rid = hop.second;
				// Identify the output port at the source router to reach the next router
				port = std::get<0>(router_list[1][src_rid][nxt_rid]);
				// This configuration needs to be done for all possible nodes attached to the destination router
				for (std::map<int,std::tuple<int,int,int>>::iterator it = router_list[0][dst_rid].begin(); it != router_list[0][dst_rid].end(); ++it) {
					nid = it->first;
					// Avoid duplicates
					if (std::find(routing_table[-1][src_rid][nid].begin(), routing_table[-1][src_rid][nid].end(), port) == routing_table[-1][src_rid][nid].end()) {
						routing_table[-1][src_rid][nid].push_back(port);
					}
				}
			}
		}	
	}
}

void simple_cycle_breaking_set_routing::compute_prev_router_map(std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>> router_list, int n_routers) const {
	// Clear the previous map
	prev_router_map.clear();
	// Variables to be reused
	int next_rid, in_port;
	// For each router, find all its neighbors and set the neighbor as its previous router for the corresponding input port
	for (int rid = 0; rid < n_routers; ++rid) {
		for (std::map<int,std::tuple<int,int,int>>::iterator it = router_list[1][rid].begin(); it != router_list[1][rid].end(); ++it) {
			next_rid = it->first;
			in_port = std::get<1>(it->second);	
			prev_router_map[next_rid][in_port] = rid;
		}
	}
}

void simple_cycle_breaking_set_routing::compute_permitted_turns(std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>> router_list, int n_routers) const {
	// Preprocessing: Compute a clean adjacency list for easier handling
	std::vector<std::vector<int>> adj_list(n_routers);
	for (int src_rid = 0; src_rid < n_routers; ++src_rid) {
		for (std::map<int,std::tuple<int,int,int>>::iterator it = router_list[1][src_rid].begin(); it != router_list[1][src_rid].end(); ++it) {
			int dst_rid = it->first;
			adj_list[src_rid].push_back(dst_rid);
		}
	}
	// Boolean vector to invalidate vertices that have been processed (removed from the graph)
	std::vector<bool> is_valid(n_routers, true);
	// Instead of n-1 iterations, we perform n-2 iterations since the case |V|==2 is only used for labeling (which we don't do) and not for forbidding turns
	for (int stage = 0; stage < n_routers - 2; ++stage) {
		// Compute the degree of each vertex; only valid vertices are considered (we operate on the graph G' that is a subgraph of G induced by the valid vertices)
		// --------------------------------------------------------------------------------------------------------------------------------------------------------
		std::vector<int> vertex_degree(n_routers, 0);
		for (int rid = 0; rid < n_routers; ++rid) {
			if (is_valid[rid]) {
				for (int nei_rid : adj_list[rid]) {
					if (is_valid[nei_rid]) {
						vertex_degree[rid]++;
					}
				}
			}
		}
		// Check for each vertex whether it is a cut-node or not. 
		// This is done by using Tarjan's algorithm to find all cut-vertices in O(V+E) time (A variant of DFS is used)
		// --------------------------------------------------------------------------------------------------------------------------------------------------------
		std::vector<bool> is_cut_vertex(n_routers, false);
		// Auxiliary data structures for Tarjan's algorithm
		// disc[i]: 	discovery time of node i in DFS order
		// low[i]:  	lowest discovery time reachable from i (including back edges)
		// parent[i]: 	DFS parent of node i
		std::vector<int> disc(n_routers, -1), low(n_routers, -1), parent(n_routers, -1);
		// Global timer for discovery times in DFS
		int tim = 0;
		// Recursive lambda function for DFS
		auto dfs = [&](auto&& self, int u) -> void {
			// Initialize discovery time and low value
			disc[u] = low[u] = tim++;
			// Count of children in DFS
			int child = 0;
			// Explore all neighbors
			for (int v : adj_list[u]) {
				// Skip invalid neighbors
				if (!is_valid[v]) continue;
				// If v is not visited yet, recurse on it
				if (disc[v] == -1) {
					// Set parent of v to u (the current node)
					parent[v] = u;
					// Increment child count for u
					++child;
					// Recursive DFS call for neighbor v
					self(self, v);
					// Update low value of u based on the low value of v
					low[u] = std::min(low[u], low[v]);
					// Rule 1: if u is the root of DFS and has two or more children, then u is a cut-vertex
					if (parent[u] == -1 && child > 1) is_cut_vertex[u] = true;
					// Rule 2: if u is not the root and no back edge from v or its descendants points to one of u's ancestors, then u is a cut-vertex
					if (parent[u] != -1 && low[v] >= disc[u]) is_cut_vertex[u] = true;
				// If v is already visited and is not the parent of u, then it's a back edge -> update low value of u
				} else if (v != parent[u]) {
					low[u] = std::min(low[u], disc[v]);
				}
			}
		};
		// Run DFS on each valid vertex that has not yet been visited (for a connected induced subgraph, this is only needed once)
		for (int i = 0; i < n_routers; ++i) {
			if (is_valid[i] && disc[i] == -1) {
				parent[i] = -1;
				dfs(dfs, i);
			}
		}
		// Identify the vertex with the smallest degree that is not a cut-vertex and that satisfies the degree condition.
		// One such vertex exists according to lemma 2 in the paper.
		// --------------------------------------------------------------------------------------------------------------------------------------------------------
		int selected_vertex_id = -1;
		int selected_vertex_degree = INT_MAX;
		int lhs_of_inquality, rhs_of_inquality;
		for (int rid = 0; rid < n_routers; ++rid) {
			// Valid vertex (i.e. not removed yet) and not a cut-vertex
			if (is_valid[rid] && !is_cut_vertex[rid]){
				// LHS only depends on the degree of the vertex
				lhs_of_inquality = vertex_degree[rid] * (vertex_degree[rid] - 1);
				// RHS depends on the degrees of the neighbors
				rhs_of_inquality = 0;
				for (int nei_rid : adj_list[rid]) {
					if (is_valid[nei_rid]) {
						rhs_of_inquality += (vertex_degree[nei_rid] - 1);
					}
				}
				// Check the degree condition
				if (lhs_of_inquality <= rhs_of_inquality) {
					// This is a valid candidate; check if it has the smallest degree found so far
					if (vertex_degree[rid] < selected_vertex_degree) {
						selected_vertex_id = rid;
						selected_vertex_degree = vertex_degree[rid];
					}
				}
			}
		}
		// Identify new prohibited turns based on the selected vertex
		// --------------------------------------------------------------------------------------------------------------------------------------------------------
		for (int prev : adj_list[selected_vertex_id]) {
			if (is_valid[prev]) {
				for (int next : adj_list[selected_vertex_id]) {
					if (is_valid[next] && next != prev) {
						std::tuple<int,int,int> turn = std::make_tuple(prev, selected_vertex_id, next);
						std::tuple<int,int,int> reverse_turn = std::make_tuple(next, selected_vertex_id, prev);
						// Make sure each turn is only added once (no duplicates)
						if (std::find(forbidden_turns.begin(), forbidden_turns.end(), turn) == forbidden_turns.end()){
							forbidden_turns.push_back(turn);
						}
						// Reverse turn
						if (std::find(forbidden_turns.begin(), forbidden_turns.end(), reverse_turn) == forbidden_turns.end()){
							forbidden_turns.push_back(reverse_turn);
						}
					}
				}
			}
		}
		// Identify new permitted turns based on the selected vertex
		// --------------------------------------------------------------------------------------------------------------------------------------------------------
		for (int next : adj_list[selected_vertex_id]) {
			if (is_valid[next]) {
				for (int nextnext: adj_list[next]) {
					if (is_valid[nextnext] && nextnext != selected_vertex_id) {
						std::tuple<int,int,int> turn = std::make_tuple(selected_vertex_id, next, nextnext);
						std::tuple<int,int,int> reverse_turn = std::make_tuple(nextnext, next, selected_vertex_id);
						// Make sure each turn is only added once (no duplicates)
						if (std::find(permitted_turns.begin(), permitted_turns.end(), turn) == permitted_turns.end()){
							permitted_turns.push_back(turn);	
						}
						// Reverse turn
						if (std::find(permitted_turns.begin(), permitted_turns.end(), reverse_turn) == permitted_turns.end()){
							permitted_turns.push_back(reverse_turn);
						}
					}
				}
			}
		}
		// Remove the selected vertex from the graph (invalidate it)
		// --------------------------------------------------------------------------------------------------------------------------------------------------------
		is_valid[selected_vertex_id] = false;
	}
}
