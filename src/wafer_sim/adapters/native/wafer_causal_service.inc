// Included only in patched IQRouter copies. No scheduling/state setter is used.
#include <fstream>
#include <stdexcept>
#include <nlohmann/json.hpp>
#include "flitchannel.hpp"
#include "islip.hpp"
#include "wafer_local_service.hpp"

namespace {
using LocalJson = nlohmann::json;
struct LocalObserver {
  long rows = 0;
  bool finished = false, enabled = false;
  bool contract_written[4] = {false, false, false, false};
  std::ofstream stream;
  LocalObserver() {
    const char *path = std::getenv("WAFER_CAUSAL_OBSERVATION");
    if (!path) return;
    enabled = true;
    if (std::ifstream(path).good()) throw std::runtime_error("Existing causal evidence");
    stream.open(path, std::ios::out);
    if (!stream) throw std::runtime_error("Cannot open causal evidence");
    write({{"kind", "begin"}, {"schema", 3}, {"scope", "four-router causal closure observation"}});
  }
  void write(const LocalJson &record) {
    if (finished) throw std::runtime_error("Observation after checked close");
    stream << record.dump() << '\n';
    if (!stream) throw std::runtime_error("Local-service evidence write failed");
    ++rows;
  }
};
LocalObserver &local_observer() { static LocalObserver value; return value; }
}

int IQRouter::_WaferLocalOutput() const {
  if (!local_observer().enabled) return -1;
  if (_id < 0 || _id > 3 || _vcs != 1 || _input_speedup != 1 || _output_speedup != 1 ||
      _speculative || _hold_switch_for_packet || _vc_alloc_delay != 1 || _sw_alloc_delay != 1 ||
      _internal_speedup != 1.0 || _routing_delay != 0 || _credit_delay != 0)
    throw std::runtime_error("Unsupported causal observation contract");
  const int selected[4] = {2, 1, 2, 0};
  int output = selected[_id];
  if (output >= _outputs) throw std::runtime_error("Causal output absent");
  const Router *sink = _output_channels[output]->GetSink();
  const int next[4] = {2, 2, 3, -1};
  if (output >= _outputs || (sink ? sink->GetID() : -1) != next[_id])
    throw std::runtime_error("Causal forward attachment mismatch");
  if (_id == 3 && _output_channels[output]->GetSinkPort() != 3)
    throw std::runtime_error("Wrong causal receiver");
  return output;
}

void IQRouter::_WaferLocalAllocation(const char *stage, bool after) const {
  const int output = _WaferLocalOutput();
  if (output < 0) return;
  const bool is_vc = std::string(stage) == "vc";
  const Allocator *allocator = is_vc ? _vc_allocator : _sw_allocator;
  const auto *islip = dynamic_cast<const iSLIP_Sparse *>(allocator);
  if (!islip || islip->WaferIterations() != 1)
    throw std::runtime_error("Observed allocator must be one-iteration iSLIP");
  if (!local_observer().contract_written[_id]) {
    local_observer().write({{"kind", "contract"}, {"router", _id}, {"output", output}, {"input_count", _inputs},
      {"crossbar_delay", _crossbar_delay}, {"channel_latency", _output_channels[output]->GetLatency()},
      {"downstream_capacity", _next_buf[output]->LimitFor(0)}, {"vc_busy_when_full", _vc_busy_when_full},
      {"output_buffer_limit", _output_buffer_size}, {"routing_delay", _routing_delay},
      {"vc_alloc_delay", _vc_alloc_delay}, {"sw_alloc_delay", _sw_alloc_delay}});
    local_observer().contract_written[_id] = true;
  }
  LocalJson rows = LocalJson::array();
  for (int input = 0; input < _inputs; ++input) {
    const Buffer *buffer = _buf[input];
    const bool empty = buffer->Empty(0);
    const Flit *head = empty ? nullptr : buffer->FrontFlit(0);
    if (head && (!head->head || !head->tail))
      throw std::runtime_error("Local observation requires single-flit packets");
    const Router *upstream = _input_channels[input]->GetSource();
    LocalJson other = LocalJson::array();
    for (int port = 0; port < _outputs; ++port)
      if (port != output && allocator->ReadRequest(input, port) >= 0) other.push_back(port);
    bool target_route = false;
    bool vc_pending = false, sw_pending = false;
    for (const auto &entry : _vc_alloc_vcs)
      vc_pending |= entry.first < 0 && entry.second.first.first == input && entry.second.first.second == 0;
    for (const auto &entry : _sw_alloc_vcs)
      sw_pending |= entry.first < 0 && entry.second.first.first == input && entry.second.first.second == 0;
    if (!empty && buffer->GetState(0) == VC::active)
      target_route = buffer->GetOutputPort(0) == output;
    else if (!empty && buffer->GetState(0) == VC::vc_alloc)
      for (const auto &route : buffer->GetRouteSet(0)->GetSet())
        target_route |= route.output_port == output;
    rows.push_back({{"input", input}, {"upstream_router", upstream ? upstream->GetID() : -1}, {"upstream_endpoint", upstream ? -1 : _input_channels[input]->GetSourcePort()},
      {"occupancy", buffer->GetOccupancy(0)}, {"state", VC::VCSTATE[buffer->GetState(0)]},
      {"head_flit", head ? head->id : -1}, {"head_message", head ? head->mid : -1},
      {"target_in_route", target_route},
      {"vc_evaluate_pending", vc_pending}, {"sw_evaluate_pending", sw_pending},
      {"requested", allocator->ReadRequest(input, output) >= 0},
      {"other_output_requests", other}});
  }
  const BufferState *downstream = _next_buf[output];
  local_observer().write({{"kind", after ? "allocate_post" : "allocate_pre"},
    {"stage", stage}, {"cycle", GetSimTime()}, {"router", _id}, {"output", output},
    {"destination", _id == 3 ? -1 : (_id == 2 ? 3 : 2)}, {"input_count", _inputs},
    {"grant_pointer", islip->WaferGrantPointer(output)},
    {"grant_input", after ? allocator->InputAssigned(output) : -1},
    {"vc_available", downstream->IsAvailableFor(0)}, {"vc_owner", downstream->UsedBy(0)},
    {"vc_busy_when_full", _vc_busy_when_full},
    {"credit_available", !downstream->IsFullFor(0)},
    {"credit_slots", downstream->AvailableFor(0)}, {"downstream_occupancy", downstream->OccupancyFor(0)},
    {"output_buffer_occupancy", _output_buffer[output].size()},
    {"output_buffer_limit", _output_buffer_size}, {"inputs", rows}});
}

void IQRouter::_WaferLocalFlit(const char *kind, int input, int output, const Flit *flit) const {
  const int selected = _WaferLocalOutput();
  if (selected < 0 || output != selected) return;
  local_observer().write({{"kind", kind}, {"cycle", GetSimTime()}, {"router", _id},
    {"output", output}, {"destination", _id == 3 ? -1 : (_id == 2 ? 3 : 2)},
    {"input", input}, {"flit", flit->id}, {"message", flit->mid}});
}

void IQRouter::_WaferLocalCredit(int output, int amount) const {
  if (_WaferLocalOutput() != output) return;
  local_observer().write({{"kind", "credit_return"}, {"cycle", GetSimTime()},
    {"amount", amount}, {"output", output}, {"router", _id}});
}

void WaferLocalServiceFinish() {
  LocalObserver &observer = local_observer();
  if (!observer.enabled) return;
  if (observer.rows <= 1) throw std::runtime_error("Selected output was not observed");
  observer.write({{"kind", "end"}, {"complete", true}, {"rows_before_end", observer.rows}});
  observer.stream.flush();
  if (!observer.stream) throw std::runtime_error("Cannot finish local-service evidence");
  observer.finished = true;
}

void IQRouter::_WaferCausalCreditSend(int input, int amount) const {
  if (!local_observer().enabled) return;
  local_observer().write({{"kind", "credit_send"}, {"cycle", GetSimTime()},
    {"router", _id}, {"input", input}, {"amount", amount}});
}
void WaferCausalEndpointCredit(int endpoint, int cycle, int amount) {
  if (!local_observer().enabled) return;
  local_observer().write({{"kind", "endpoint_credit"}, {"cycle", cycle},
    {"endpoint", endpoint}, {"amount", amount}});
}
