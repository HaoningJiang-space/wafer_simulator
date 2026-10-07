#pragma once
#include "selection_function.hpp"
#include <vector>
#include <tuple>
#include <map>

class balancing_selection : public selection_function {
public:
    balancing_selection() = default;
    std::tuple<int,int,int>
    select(int rid,std::vector<std::tuple<int,int,int>> valid_next_hops) const override;
private:
	// flits_per_port[router_id][port_id] = number of flits sent through port_id of router_id
	mutable std::map<int,std::map<int,long long>> flits_per_port;
};
