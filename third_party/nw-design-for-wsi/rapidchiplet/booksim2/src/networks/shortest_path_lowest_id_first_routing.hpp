#pragma once
#include "routing_function.hpp"
#include <vector>
#include <tuple>
#include <map>

class shortest_path_lowest_id_first_routing : public routing_function {
public:
    shortest_path_lowest_id_first_routing() = default;
	// router_list[0][router_id][node_id] = (port, latency)
	// router_list[1][router_id][other_router_id] = (port, latency)
	// return: (out_port, vc_start, vc_end)
    std::vector<std::tuple<int,int,int>> route(std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>> router_list, int n_routers, int n_nodes, int n_vcs, int cur_rid, int dst_nid, int in_port, int flit_id) const override;
private:
	// routing_table[cur_router_id][dst_node_id] = port
    mutable std::map<int,std::map<int,int>> routing_table;
	// router_list[0][router_id][node_id] = (port, latency)
	// router_list[1][src_router_id][dst_router_id] = (output_port_at_src, input_port_at_dst, latency)
    void route_from_source(std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>> router_list, int n_routers, int n_nodes, int src_rid) const;
};
