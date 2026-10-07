#include "ChannelDependencyGraph.hpp"
#include <stack>
#include <set>
#include <map>
#include <vector>
#include <utility>
#include <functional>
#include <algorithm>

// Builds the channel dependency graph from the routing function and router list
// TODO: This currently ignores VCs and only analyzes the physical channels
ChannelDependencyGraph::ChannelDependencyGraph(const std::map<int,int>& node_list, const std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>>& router_list, int n_routers, int n_nodes, int n_vcs, const routing_function& rf) {
	// Local variables
	// port_list[src_rid][port] = dst_rid
	std::map<int, std::map<int, int>> out_port_list;
	// Helper variables only allocated once
	std::vector<std::tuple<int,int,int>> valid_next_hops;
	std::tuple<int,int,int> next_hop;
	std::vector<std::tuple<int,int,int>> hops;		// prev_rid, cur_rid, in_port
	std::vector<std::tuple<int,int,int>> new_hops;	// prev_rid, cur_rid, in_port
	int src_rid, dst_rid, prev_rid, cur_rid, next_rid;
	int src_nid, dst_nid;
	int out_port, in_port, next_in_port;
	// Initialize port_list and cdg_adj_list
	for (std::map<int,std::map<int,std::tuple<int,int,int>>>::const_iterator sit = router_list[1].begin(); sit != router_list[1].end(); ++sit) {
		src_rid = sit->first;
		for (std::map<int,std::tuple<int,int,int>>::const_iterator dit = sit->second.begin(); dit != sit->second.end(); ++dit) {
			dst_rid = dit->first;
			out_port = std::get<0>(dit->second);
			out_port_list[src_rid][out_port] = dst_rid;
			cdg_adj_list[std::make_pair(src_rid, dst_rid)] = std::vector<std::pair<int,int>>{};
		}
	}
	// Construct the Channel Dependency Graph
	int flit_id = 0; // Needed for routing, we use one flit-ID per src-dst pair
	for (src_nid = 0; src_nid < n_nodes; ++src_nid) {
		src_rid = node_list.at(src_nid);
		for (dst_nid = 0; dst_nid < n_nodes; ++dst_nid) {
			in_port = std::get<1>(router_list[0].at(src_rid).at(src_nid));
			// Due to the possibility of multiple paths, we need to track a series of concurrent hops
			// Each hop is given as a (cur_rid
			hops.clear();
			hops.push_back(std::make_tuple(-1, src_rid, in_port));
			// Continue until we reached the router connected to the destination node
			while (!hops.empty()) {
				new_hops.clear();
				// Iterate through all current hops
				for (std::vector<std::tuple<int,int,int>>::const_iterator hit = hops.begin(); hit != hops.end(); ++hit) {
					prev_rid = std::get<0>(*hit);
					cur_rid = std::get<1>(*hit);
					in_port = std::get<2>(*hit);
					// We only need to do something if the destination has not been reached
					if (cur_rid != node_list.at(dst_nid)) {
						valid_next_hops = rf.route(router_list, n_routers, n_nodes, n_vcs, cur_rid, dst_nid, in_port, flit_id);
						// For each valid next hop, create a new hop and add it to new_hops
						for (std::vector<std::tuple<int,int,int>>::const_iterator vhit = valid_next_hops.begin(); vhit != valid_next_hops.end(); ++vhit) {
							out_port = std::get<0>(*vhit);
							next_rid = out_port_list[cur_rid][out_port];
							next_in_port = std::get<1>(router_list[1].at(cur_rid).at(next_rid));
							// Add the new hop to the list, but only if it does not exist yet. This allows the re-convergence of paths

							if (std::find(new_hops.begin(), new_hops.end(), std::make_tuple(cur_rid, next_rid, next_in_port)) == new_hops.end()){
								new_hops.push_back(std::make_tuple(cur_rid, next_rid, next_in_port));
							}
							// If there was a previous router, add an edge to the CDG
							if (prev_rid != -1) {
								std::pair<int,int> cdg_src_vertex = std::make_pair(prev_rid, cur_rid);
								std::pair<int,int> cdg_dst_vertex = std::make_pair(cur_rid, next_rid);
								// Only add an edge if it is not already present
								// Since the cdg_adj_list is initialized with all possible vertices, cdg_src_vertex must exist, otherwise there is a bug
								if (std::find(cdg_adj_list[cdg_src_vertex].begin(), cdg_adj_list[cdg_src_vertex].end(), cdg_dst_vertex) == cdg_adj_list[cdg_src_vertex].end()){
									cdg_adj_list[cdg_src_vertex].push_back(cdg_dst_vertex);
								}	
							}
						}
					}
				}
				hops = new_hops;
			}
			++flit_id;
		}
	}
}

bool ChannelDependencyGraph::is_acyclic() const {
	// Data structures for DFS
    std::set<std::pair<int,int>> visited;
    std::set<std::pair<int,int>> stack;

	// Use adjacency list for easier traversal
    std::function<bool(const std::pair<int,int>&)> dfs = [&](const std::pair<int,int>& u) -> bool {
            if (stack.count(u) > 0) return true;		// Cycle detected
            if (visited.count(u) > 0) return false;		// Already visited node, no cycle from this node
			// Mark the current node as visited and add to recursion stack
            visited.insert(u);
            stack.insert(u);
			// Recur for all neighbors
            std::map<std::pair<int,int>, std::vector<std::pair<int,int>>>::const_iterator it = cdg_adj_list.find(u);
            if (it != cdg_adj_list.end()) {
                const std::vector<std::pair<int,int>>& neighbors = it->second;
                for (std::vector<std::pair<int,int>>::const_iterator vit = neighbors.begin(); vit != neighbors.end(); ++vit) {
                    if (dfs(*vit)) return true;			// Cycle detected in the recursion
                }
            }
            stack.erase(u);
            return false;								// No cycle detected from this node
        };
	// Call the recursive helper function to detect cycle in different DFS trees
    for (std::map<std::pair<int,int>, std::vector<std::pair<int,int>>>::const_iterator it = cdg_adj_list.begin(); it != cdg_adj_list.end(); ++it) {
        const std::pair<int,int>& node = it->first;
        if (visited.count(node) == 0 && dfs(node)) {
            return false;								// Cycle found, graph is not acyclic		
        }
    }
	return true;										// No cycles found, graph is acyclic
}

