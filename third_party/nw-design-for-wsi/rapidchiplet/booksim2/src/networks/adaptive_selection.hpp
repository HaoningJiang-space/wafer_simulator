#pragma once
#include "selection_function.hpp"
#include <vector>
#include <tuple>

// Forward declaration of Router to avoid circular dependency
class Router; 

class adaptive_selection : public selection_function {

public:
    // Constructor that accepts the pointer to the vector
    explicit adaptive_selection(std::vector<Router*>* router_object_list) : router_object_list_(router_object_list) {}
    std::tuple<int,int,int> select(int rid, std::vector<std::tuple<int,int,int>> valid_next_hops) const override;
private:
    std::vector<Router*>* router_object_list_; 
};
