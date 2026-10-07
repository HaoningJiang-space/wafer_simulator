#pragma once
#include "routing_function.hpp"
#include <vector>
#include <tuple>
#include <map>

class Configuration;

class xy_routing : public routing_function {
public:
    explicit xy_routing(const Configuration& config, std::map<int,int> node_list) : config_(config), node_list_(std::move(node_list)) {
		read_xy_info();
	}
	// router_list[0][router_id][node_id] = (port, latency)
	// router_list[1][router_id][other_router_id] = (port, latency)
	// return: (out_port, vc_start, vc_end)
    std::vector<std::tuple<int,int,int>> route(std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>> router_list, int n_routers, int n_nodes, int n_vcs, int cur_rid, int dst_nid, int in_port, int flit_id) const override;
private:
	const Configuration& config_;
	std::map<int,int> node_list_;
	// xy_info[router_id] = (x, y, next_rid_north, next_rid_east, next_rid_south, next_rid_west)
    mutable std::vector<std::tuple<float,float,int,int,int,int>> xy_info;
	mutable std::map<int,bool> x_coordinate_reached;
    void read_xy_info() const;
};
