// Correctness only: node ownership, key ordering, duplicates and credit reset.
#include "booksim.hpp"
#include "credit.hpp"
#include "node_reuse.hpp"
#include <iostream>
#include <random>

int main() {
  std::map<int, int> values, expected;
  std::vector<std::map<int, int>::node_type> map_pool;
  values[1] = 2;
  const auto * address = &*values.begin();
  RecycleNodes(values, map_pool);
  ReuseMapEntry(values, map_pool, 3, 4);
  assert(&*values.begin() == address);  // The allocation itself is reused.
  values.clear();
  std::mt19937 rng(17);
  for (int step = 0; step < 10000; ++step) {
    int key = rng() % 31, value = rng() % 1000;
    if (step % 37 == 0) {
      RecycleNodes(values, map_pool);
      expected.clear();
    } else {
      ReuseMapEntry(values, map_pool, key, value);
      expected[key] = value;
    }
    assert(values == expected);
  }
  std::set<int> keys, expected_keys;
  std::vector<std::set<int>::node_type> set_pool;
  for (int step = 0; step < 10000; ++step) {
    int key = rng() % 31;
    if (step % 37 == 0) {
      RecycleNodes(keys, set_pool);
      expected_keys.clear();
    } else {
      ReuseSetEntry(keys, set_pool, key);
      expected_keys.insert(key);
    }
    assert(keys == expected_keys);
  }
  Credit * first = Credit::New(), * second = Credit::New();
  for (int round = 0; round < 100; ++round) {
    for (int vc : {7, 3, 1, 3, 0, 7}) first->AddVC(vc);
    second->AddVC(2);
    assert(first->vc == std::set<int>({0, 1, 3, 7}));
    assert(second->vc == std::set<int>({2}));
    assert(Credit::OutStanding() == 2);
    first->head = first->tail = true;
    first->id = 19;
    first->Free();
    Credit * reused = Credit::New();
    assert(reused == first && reused->vc.empty());
    assert(!reused->head && !reused->tail && reused->id == -1);
    assert(second->vc == std::set<int>({2}));
  }
  first->Free();
  second->Free();
  assert(Credit::OutStanding() == 0);
  Credit::FreeAll();
  std::cout << "node ownership, ordered values, duplicates and multi-VC credit reuse: PASS\n";
}
