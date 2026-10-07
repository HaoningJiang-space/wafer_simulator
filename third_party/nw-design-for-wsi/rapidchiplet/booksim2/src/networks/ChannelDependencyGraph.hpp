#pragma once
#include "routing_function.hpp"
#include "selection_function.hpp"
#include <vector>
#include <map>
#include <tuple>
#include <utility>   // for std::pair
#include <vector>

class ChannelDependencyGraph {
public:
    ChannelDependencyGraph(const std::map<int,int>& node_list, const std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>>& router_list, int n_routers, int n_nodes, int n_vcs, const routing_function& rf);

    bool is_acyclic() const;

private:
	// Adjacency list where channels, i.e.,  (rid,rid)-pairs are nodes
    std::map<std::pair<int,int>, std::vector<std::pair<int,int>>> cdg_adj_list;
};

