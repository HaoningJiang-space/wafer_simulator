// Online adapter around the unchanged, patched author TrafficManager.
// No router, VC, credit, arbitration or packet-generation implementation is copied.
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
#include <nlohmann/json.hpp>
#include "booksim_config.hpp"
#include "trafficmanager.hpp"
#include "network.hpp"
#include "router.hpp"
#include "flitchannel.hpp"
#include "credit.hpp"
#include "routefunc.hpp"

using json = nlohmann::json;
extern TrafficManager *trafficManager;
extern long global_current_cycle;

class OnlineTrafficManager : public TrafficManager {
    std::vector<json> finished;
    std::map<int, std::vector<int>> paths;
    std::map<int, json> hops;
    std::map<int, int> injection_arrivals;
    std::vector<json> message_flits;
    long steps = 0, skipped = 0;

    void ObserveChannels() {
        // Channel::Receive is a non-destructive accessor. Observe before the
        // normal _Step consumes the outputs and retires/frees any flits.
        for (auto *net : _net) {
            for (auto *ch : net->GetInject()) {
                if (Flit *f = ch->Receive()) {
                    paths[f->id].push_back(ch->GetSink()->GetID());
                    injection_arrivals[f->id] = _time;
                }
            }
            for (auto *ch : net->GetChannels()) {
                if (Flit *f = ch->Receive()) {
                    paths[f->id].push_back(ch->GetSink()->GetID());
                    if (!hops.count(f->id)) hops[f->id] = json::array();
                    hops[f->id].push_back({{"source", ch->GetSource()->GetID()},
                        {"destination", ch->GetSink()->GetID()}, {"cycle", _time}, {"vc", f->vc}});
                }
            }
        }
    }

    void _RetireFlit(Flit *f, int dest) override {
        const int mid = f->mid;
        message_flits.at(mid).push_back({{"id", f->id}, {"message", mid},
            {"source", f->src}, {"destination", dest}, {"generated", f->ctime},
            {"injected", f->itime}, {"ejected", f->atime}, {"hops", f->hops},
            {"router_path", paths.at(f->id)}, {"injection_router_arrival", injection_arrivals.at(f->id)},
            {"link_arrivals", hops.count(f->id) ? hops.at(f->id) : json::array()}});
        paths.erase(f->id); hops.erase(f->id); injection_arrivals.erase(f->id);
        if (msg_flits_remaining.at(mid) == 0) {
            finished.push_back({{"id", mid}, {"source", msg_source.at(mid)},
                {"destination", msg_destination.at(mid)}, {"ready", msg_ready_cycle.at(mid)},
                {"generated", msg_generate_cycle.at(mid)},
                {"first_inject", msg_first_inject.at(mid)}, {"last_inject", msg_last_inject.at(mid)},
                {"first_eject", msg_first_eject.at(mid)}, {"last_eject", global_current_cycle},
                // Cycle t is the interval [t,t+1). Publish at its end boundary.
                {"finish", global_current_cycle+1}, {"flits", message_flits.at(mid)}});
        }
        TrafficManager::_RetireFlit(f, dest);
    }

    void Step() {
        global_current_cycle = _time;
        ObserveChannels();
        if (_Step() != 0) throw std::runtime_error("Native network failed/deadlocked");
        ++steps;
        global_current_cycle = _time;
    }

public:
    OnlineTrafficManager(const Configuration &config, const std::vector<Network *> &net)
        : TrafficManager(config, net) {
        if (rc_mode != "trace" || rc_trace_instructions != 0 || _classes != 1 || _subnets != 1)
            throw std::runtime_error("Online mode requires empty trace, one class and one subnet");
        _time = 0; global_current_cycle = 0;
        _sim_state = running;
        _requestsOutstanding.assign(_nodes, 0);
        for (int s = 0; s < _nodes; ++s) {
            _qtime[s].assign(_classes, 0); _qdrained[s].assign(_classes, false);
        }
        _ClearStats();
        for (int c = 0; c < _classes; ++c) {
            _traffic_pattern[c]->reset(); _injection_process[c]->reset();
        }
    }

    bool Idle() const {
        if (Credit::OutStanding() != 0) return false;
        for (const auto &rows : _total_in_flight_flits) if (!rows.empty()) return false;
        for (const auto &entry : ready_messages) if (!entry.second.empty()) return false;
        return true;
    }

    json Submit(const json &request) {
        int id = request.at("id"), src = request.at("source"), dst = request.at("destination");
        int count = request.at("flits");
        if (id != static_cast<int>(msg_source.size()) || request.at("cycle").get<int>() != _time ||
            src < 0 || src >= _nodes || dst < 0 || dst >= _nodes || src == dst || count <= 0)
            throw std::runtime_error("Invalid online message or clock");
        // Append one dependency-free message only when the external executor
        // makes it ready. All injection and all-flit completion remain native.
        msg_source.push_back(src); msg_destination.push_back(dst);
        msg_deps_left.push_back(0); msg_cycle.push_back(_time);
        msg_packets.push_back(count); msg_ignore.push_back(0); msg_duration.push_back(0);
        msg_ready_cycle.push_back(-1); msg_finish_cycle.push_back(-1); msg_generate_cycle.push_back(-1);
        msg_start_cycle.push_back(-1); msg_cpu_predecessor.push_back(-1); msg_cpu_resource.push_back(-1);
        msg_first_inject.push_back(-1); msg_last_inject.push_back(-1); msg_first_eject.push_back(-1);
        msg_flits_remaining.push_back(count); trace_scheduled.push_back(0); trace_completed.push_back(0);
        trace_dependencies.offsets.push_back(0);
        message_flits.push_back(json::array());
        ++rc_trace_instructions;
        _HandlePacketWithZeroDependencies(id);
        return {{"ok", true}, {"cycle", _time}, {"id", id}};
    }

    json Advance(int limit) {
        if (limit < _time || limit > 1000000000) throw std::runtime_error("Invalid advance boundary");
        finished.clear();
        while (_time < limit) {
            if (Idle()) { skipped += limit-_time; _time=limit; global_current_cycle=_time; break; }
            Step();
            if (!finished.empty()) break;
        }
        return {{"ok", true}, {"cycle", _time}, {"completed", finished}, {"idle", Idle()}};
    }

    json Close() {
        if (rc_trace_instructions_simulated != rc_trace_instructions)
            throw std::runtime_error("Cannot close with unfinished messages");
        const int limit = _time+100000;
        while (!Idle() && _time < limit) Step();
        if (!Idle()) throw std::runtime_error("Credits did not drain");
        return {{"ok", true}, {"cycle", _time}, {"messages", rc_trace_messages_simulated},
                {"flits", rc_trace_ejected_flits}, {"steps", steps}, {"idle_skipped_cycles", skipped},
                {"drained", true}};
    }
    int Nodes() const { return _nodes; }
};

int main(int argc, char **argv) {
    if (argc != 3) { std::cerr << "Usage: online_booksim CONFIG RESPONSE_FD\n"; return 2; }
    std::ofstream replies(std::string("/proc/self/fd/")+argv[2]);
    if (!replies) return 2;
    try {
        BookSimConfig config;
        if (!ParseArgs(&config, 2, argv)) throw std::runtime_error("Invalid configuration");
        InitializeRoutingMap(config);
        gPrintActivity=false; gTrace=false; gWatchOut=nullptr;
        std::vector<Network *> networks;
        for (int i=0; i<config.GetInt("subnets"); ++i)
            networks.push_back(Network::New(config, "network_"+std::to_string(i)));
        auto *manager = new OnlineTrafficManager(config, networks);
        trafficManager = manager;
        replies << json({{"ok",true},{"ready",true},{"cycle",0},{"nodes",manager->Nodes()}}).dump() << std::endl;
        std::string line;
        bool closed=false;
        while (std::getline(std::cin,line)) {
            const auto request=json::parse(line);
            const std::string command=request.at("command");
            json reply;
            if (command == "submit") reply=manager->Submit(request);
            else if (command == "advance") reply=manager->Advance(request.at("until"));
            else if (command == "close") { reply=manager->Close(); closed=true; }
            else throw std::runtime_error("Unknown online command");
            replies << reply.dump() << std::endl;
            if (closed) break;
        }
        if (!closed) throw std::runtime_error("EOF before checked close");
        delete manager; trafficManager=nullptr;
        for (auto *network : networks) delete network;
    } catch (const std::exception &error) {
        replies << json({{"ok",false},{"error",error.what()}}).dump() << std::endl;
        std::cerr << error.what() << std::endl;
        return 1;
    }
    return 0;
}
