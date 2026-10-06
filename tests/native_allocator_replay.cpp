// Deterministic correctness replay, linked against each actual implementation.
// No simulation timings or performance measurements are produced here.
#include "booksim.hpp"
#include "booksim_config.hpp"
#include "allocator.hpp"
#include <iostream>
#include <memory>
#include <random>
#include <vector>

int main() {
  BookSimConfig config;
  config.Assign("arb_type", "round_robin");
  for (const char * kind : {"separable_input_first", "separable_output_first", "islip"}) {
    std::unique_ptr<Allocator> allocator(Allocator::NewAllocator(nullptr, kind, kind, 8, 8, &config));
    assert(allocator);
    std::mt19937 rng(71);
    for (int round = 0; round < 500; ++round) {
      allocator->Clear();
      int labels[8][8];
      for (int in = 0; in < 8; ++in) {
        for (int out = 0; out < 8; ++out) {
          labels[in][out] = -1;
          if (rng() % 3 == 0) continue;
          int label = round * 64 + in * 8 + out;
          int in_priority = rng() % 4, out_priority = rng() % 4;
          allocator->AddRequest(in, out, label, in_priority, out_priority);
          labels[in][out] = label;
          if (rng() % 5 == 0) {
            allocator->RemoveRequest(in, out, label);
            labels[in][out] = -1;
          }
        }
      }
      for (int in = 0; in < 8; ++in)
        for (int out = 0; out < 8; ++out)
          assert(allocator->ReadRequest(in, out) == labels[in][out]);
      allocator->Allocate();
      std::cout << kind << ' ' << round;
      std::set<int> used;
      for (int in = 0; in < 8; ++in) {
        int out = allocator->OutputAssigned(in);
        std::cout << ' ' << out;
        if (out >= 0) {
          assert(labels[in][out] >= 0 && used.insert(out).second);
          assert(allocator->InputAssigned(out) == in);
        }
      }
      std::cout << '\n';
    }
  }
}
