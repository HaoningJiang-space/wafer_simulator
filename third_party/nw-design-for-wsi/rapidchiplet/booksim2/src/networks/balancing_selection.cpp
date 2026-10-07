#include "balancing_selection.hpp"
#include <vector>
#include <tuple>
#include <random>
#include <iostream>
#include <cassert>

// Balance the selection of output ports without any congestion information
std::tuple<int,int,int> balancing_selection::select(int rid, std::vector<std::tuple<int,int,int>> valid_next_hops) const {
	if (valid_next_hops.empty()) {
		std::cout << "Error: No valid next hops available for random selection function." << std::endl;
		assert(false);
	}
	// Check if the rid is present in the  follwoing map, if not, add it
	// mutable std::map<int,std::map<int,long long>> flits_per_port;
	if (flits_per_port.find(rid) == flits_per_port.end()) {
		flits_per_port[rid] = std::map<int,long long>();
	}	
	// Check if all the ports are present in the map, if not, add them
	for (const auto& hop : valid_next_hops) {
		int port = std::get<0>(hop);
		if (flits_per_port[rid].find(port) == flits_per_port[rid].end()) {
			flits_per_port[rid][port] = 0;
		}
	}
	// Find the minimum number of flits among the valid next hops
	long long min_flits = std::numeric_limits<long long>::max();
	for (const auto& hop : valid_next_hops) {
		int port = std::get<0>(hop);
		if (flits_per_port[rid][port] < min_flits) {
			min_flits = flits_per_port[rid][port];
		}
	}
	// Collect all the ports with the minimum number of flits
	std::vector<std::tuple<int,int,int>> candidates;
	for (const auto& hop : valid_next_hops) {
		int port = std::get<0>(hop);
		if (flits_per_port[rid][port] == min_flits) {
			candidates.push_back(hop);
		}
	}
	// Randomly select one of the candidates
	std::tuple<int,int,int> selected_hop = candidates[rand() % candidates.size()];
	// Increment the flit count for the selected port
	int selected_port = std::get<0>(selected_hop);
	flits_per_port[rid][selected_port]++;
	// Return the selected hop
	return selected_hop;
}

