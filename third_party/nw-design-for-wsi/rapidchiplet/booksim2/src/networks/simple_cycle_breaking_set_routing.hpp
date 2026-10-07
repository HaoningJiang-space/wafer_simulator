#pragma once
#include "routing_function.hpp"
#include <vector>
#include <tuple>
#include <map>

class simple_cycle_breaking_set_routing : public routing_function {
public:
    simple_cycle_breaking_set_routing() = default;
	// router_list[0][router_id][node_id] = (port, latency)
	// router_list[1][router_id][other_router_id] = (port, latency)
	// return: (out_port, vc_start, vc_end)
    std::vector<std::tuple<int,int,int>> route(std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>> router_list, int n_routers, int n_nodes, int n_vcs, int cur_rid, int dst_nid, int in_port, int flit_id) const override;
private:
	// routing_table[prev_router_id][cur_router_id][dst_node_id] = (out_port_1, ..., out_port_n)
    mutable std::map<int,std::map<int,std::map<int,std::vector<int>>>> routing_table;
	// maps the input channel of each router to the previous router id
	mutable std::map<int,std::map<int,int>> prev_router_map;
	// stores permitted and forbidden turns as (prev_router_id, cur_router_id, next_router_id)
	mutable std::vector<std::tuple<int,int,int>> permitted_turns;
    mutable std::vector<std::tuple<int,int,int>> forbidden_turns;
	// router_list[0][router_id][node_id] = (port, latency)
	// router_list[1][src_router_id][dst_router_id] = (output_port_at_src, input_port_at_dst, latency)
    void route_from_source(std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>> router_list, int n_routers, int n_nodes, int src_rid) const;
	void compute_prev_router_map(std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>> router_list, int n_routers) const;
	void compute_permitted_turns(std::vector<std::map<int, std::map<int, std::tuple<int, int, int>>>> router_list, int n_routers) const;
};
