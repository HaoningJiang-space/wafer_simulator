#include "xy_routing.hpp"
#include <vector>
#include <tuple>
#include <map>
#include <set>
#include <cmath>
#include <climits>
#include <iostream>
#include <fstream>
#include <sstream>

#include "config_utils.hpp"

// Deadlock-free: YES
// Minimal: YES
// Deterministic: YES (only one output port is returned)
// Description: XY routing based on external info on N,E, S, W neighbors and router position 
// Settings: Shortest paths w.r.t. hops vs. shortest paths w.r.t. latency
std::vector<std::tuple<int,int,int>> xy_routing::route(std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>> router_list, int n_routers, int n_nodes, int n_vsc, int cur_rid, int dst_nid, int in_port, int flit_id) const {
	float epsilon = 0.01;	// Small value to handle floating point comparisons
	int dst_rid = node_list_.at(dst_nid);
	float cur_x, cur_y, dst_x, dst_y;
	int n, e, s, w;
	int nxt_rid = -1;
	int out_port = -1;
	std::tie(cur_x, cur_y, n, e, s, w) = xy_info[cur_rid];
	std::tie(dst_x, dst_y, std::ignore, std::ignore, std::ignore, std::ignore) = xy_info[dst_rid];
	// Check if the current flit has reached the destination router and needs to be ejected
	if (cur_rid == dst_rid) {
		out_port = std::get<0>(router_list[0][cur_rid][dst_nid]);
	} else {
		// Check if the current flit is in the x_coordinate_reached map.
		if (x_coordinate_reached.find(flit_id) == x_coordinate_reached.end()) {
			x_coordinate_reached[flit_id] = false;
		}
		// Check if this flit has reached the x coordinate of the destination
		if (!x_coordinate_reached[flit_id] && fabs(cur_x - dst_x) <= epsilon) {
			x_coordinate_reached[flit_id] = true;
		}
		// If x coordinate not yet reached, route in x direction
		if (!x_coordinate_reached[flit_id]) {
			if (dst_x > cur_x + epsilon) {
				nxt_rid = e;	// Route East
			} else if (dst_x < cur_x - epsilon) {
				nxt_rid = w;	// Route West
			} else {
				std::cerr << "Error: Flit " << flit_id << " at router " << cur_rid << " has not reached x coordinate but current x equals destination x." << std::endl;
			}
		} else {
			if (dst_y > cur_y + epsilon) {
				nxt_rid = n;	// Route North
			} else if (dst_y < cur_y - epsilon) {
				nxt_rid = s;	// Route South
			} else {
				std::cerr << "Error: Flit " << flit_id << " at router " << cur_rid << " has reached x coordinate but current y equals destination y." << std::endl;
			}
		}
		out_port = std::get<0>(router_list[1][cur_rid][nxt_rid]);
	}
	// Return the output port; Allow the full range of possible VCs
	return {std::make_tuple(out_port, 0, n_vsc-1)};
}


void xy_routing::read_xy_info() const {
	    // NOTE: The filename should ideally be configurable, but is hardcoded for brevity here.
    const std::string filename = config_.GetStr("path_for_xy_info");

    // Use std::ifstream to open the file
    std::ifstream file(filename);

    if (!file.is_open()) {
        std::cerr << "Error: Could not open data file: " << filename << std::endl;
        return;
    }

    xy_info.clear();
    std::string line;
    float x, y;
    int n, e, s, w;
    char delim; // Used to consume the comma delimiter

    // Read the file line by line
    while (std::getline(file, line)) {
        // Skip empty lines or lines with only whitespace
        if (line.empty() || line.find_first_not_of(" \t\r\n") == std::string::npos) continue;

        std::stringstream ss(line);

        // Compact stream parsing: attempts to read the 6 values sequentially,
        // using 'delim' to consume the comma separator after each value.
        // The expression chain short-circuits on the first failure.
        if (ss >> x >> delim && delim == ',' &&
            ss >> y >> delim && delim == ',' &&
            ss >> n >> delim && delim == ',' &&
            ss >> e >> delim && delim == ',' &&
            ss >> s >> delim && delim == ',' &&
            ss >> w)
        {
            // If all 6 extractions (including delimiters) succeeded
            xy_info.emplace_back(x, y, n, e, s, w);
        } else {
            // Log a warning if the line did not match the expected six-field format
            std::cerr << "Warning: Skipped malformed/incomplete line: " << line << std::endl;
        }
    }
}

