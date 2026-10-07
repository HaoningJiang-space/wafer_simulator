#pragma once
#include "selection_function.hpp"
#include <vector>
#include <tuple>

class random_selection : public selection_function {
public:
    random_selection() = default;
    std::tuple<int,int,int>
    select(int rid, std::vector<std::tuple<int,int,int>> valid_next_hops) const override;
};
