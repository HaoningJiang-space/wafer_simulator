#pragma once
#include <vector>
#include <tuple>

class selection_function {
public:
    virtual ~selection_function() = default;
    virtual std::tuple<int,int,int> select(int rid, std::vector<std::tuple<int,int,int>> valid_next_hops) const = 0;
};

