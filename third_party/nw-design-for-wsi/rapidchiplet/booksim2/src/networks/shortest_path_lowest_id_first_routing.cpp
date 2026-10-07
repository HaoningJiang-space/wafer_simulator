#include "shortest_path_lowest_id_first_routing.hpp"
#include <vector>
#include <tuple>
#include <map>
#include <set>
#include <climits>

// Deadlock-free: NO
// Minimal: YES
// Deterministic: YES (only one output port is returned)
// Description: Shortest path routing with lowest ID first tie-breaking
// Settings: Shortest paths w.r.t. hops vs. shortest paths w.r.t. latency
std::vector<std::tuple<int,int,int>> shortest_path_lowest_id_first_routing::route(std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>> router_list, int n_routers, int n_nodes, int n_vsc, int cur_rid, int dst_nid, int in_port, int flit_id) const {
	// If the routing table has been precomputed for the current router, then compute it
	if (routing_table.find(cur_rid) == routing_table.end() || routing_table.at(cur_rid).find(dst_nid) == routing_table.at(cur_rid).end()) {
		route_from_source(router_list, n_routers, n_nodes, cur_rid);
	}
	// Read the output port from the routing table
	// Here, we only return a single output port (deterministic routing)
	int out_port = routing_table[cur_rid][dst_nid];
	// Return the output port; Allow the full range of possible VCs
	return {std::make_tuple(out_port, 0, n_vsc-1)};
}

// Computes shortest paths from the source router to all nodes in the network and sets the routing table accordingly
// Only sets the routing table entries of the current source router (cur_rid)
void shortest_path_lowest_id_first_routing::route_from_source(std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>> router_list, int n_routers, int n_nodes, int src_rid) const {
	// TODO: Hard-coded distance metric: true = latency, false = hops
	bool use_latency_for_distance = false;
	// Data structures for Dijkstra's algorithm
	std::vector<int> dist(n_routers, INT_MAX);
	std::vector<int> prev(n_routers, -1);
	std::set<int> todo;
	// Auxiliary variables (allocate only once)
	int link_latency;
	int nei_rid;
	int new_distance;
	int nid;
	int port;
	// Initialize the source router
	dist[src_rid] = 0;
	todo.insert(src_rid);
	// Dijkstra's algorithm main loop
	while (!todo.empty()) {
		// Find the router with the smallest distance (and lowest ID in case of ties)
		int cur_rid = -1;
		for (int rid : todo) {
			if (cur_rid == -1 || dist[rid] < dist[cur_rid] || (dist[rid] == dist[cur_rid] && rid < cur_rid)) {
				cur_rid = rid;
			}
		}
		todo.erase(cur_rid);
		// Explore neighbors of the current router
		for (std::map<int,std::tuple<int,int,int>>::iterator it = router_list[1][cur_rid].begin(); it != router_list[1][cur_rid].end(); ++it) {
			nei_rid = it->first;	
			link_latency = std::get<2>(it->second);
			new_distance = dist[cur_rid] + (use_latency_for_distance ? link_latency : 1);
			if (new_distance < dist[nei_rid]) {
				dist[nei_rid] = new_distance;
				prev[nei_rid] = cur_rid;
				todo.insert(nei_rid);
			} else if (new_distance == dist[nei_rid] && cur_rid < prev[nei_rid]) {
				prev[nei_rid] = cur_rid;
			}
		}
	}
	// Use back-tracking to set the routing table entries for all nodes in the network
	for (int dst_rid = 0; dst_rid < n_routers; ++dst_rid) {
		// Source router: 
		if (dst_rid == src_rid) {
			// Add the correct output port for all local nodes
			for (std::map<int,std::tuple<int,int,int>>::iterator it = router_list[0][src_rid].begin(); it != router_list[0][src_rid].end(); ++it) {
				nid = it->first;		
				port = std::get<0>(it->second);
				routing_table[src_rid][nid] = port;	
			}
		// Other routers:
		} else {
			// Back-track to find the next hop and set the output port accordingly
			nei_rid = dst_rid;		
			while (prev[nei_rid] != src_rid && prev[nei_rid] != -1) {
				nei_rid = prev[nei_rid];
			}
			port = std::get<0>(router_list[1][src_rid][nei_rid]);
			// Add that direction for all nodes that are attached to that destination router
			for (std::map<int,std::tuple<int,int,int>>::iterator it = router_list[0][dst_rid].begin(); it != router_list[0][dst_rid].end(); ++it) {
				nid = it->first;		
				routing_table[src_rid][nid] = port;
			}
		}	
	}
}
