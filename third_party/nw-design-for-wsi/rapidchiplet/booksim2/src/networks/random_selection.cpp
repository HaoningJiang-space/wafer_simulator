#include "random_selection.hpp"
#include <vector>
#include <tuple>
#include <random>
#include <iostream>
#include <cassert>

// Selects a random next hop from the list of valid next hops
std::tuple<int,int,int> random_selection::select(int rid, std::vector<std::tuple<int,int,int>> valid_next_hops) const {
	if (valid_next_hops.empty()) {
		std::cout << "Error: No valid next hops available for random selection function." << std::endl;
		assert(false);
	}
	return valid_next_hops[rand() % valid_next_hops.size()];
}

