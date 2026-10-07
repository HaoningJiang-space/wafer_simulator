#pragma once
#include <vector>
#include <tuple>
#include <map>

class routing_function {
public:
    virtual ~routing_function() = default;
    virtual std::vector<std::tuple<int,int,int>> route(std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>> router_list, int n_routers, int n_nodes, int n_vcs, int cur_rid, int dst_nid, int in_port, int flit_id) const = 0;
};

