// Endpoint-only extension; linked with the reviewed hooks in an isolated build.
// Router scheduling, internal buffers, routing, links and packet generation are reused.
#include <deque>
#include "iq_router.hpp"

class BoundaryTrafficManager : public OnlineTrafficManager {
    BookSimConfig original;
    bool enabled=false, bounded=false, streaming=false;
    int slots=0;
    std::vector<int> supplied, sent;
    std::map<int,int> ordinals;
    std::map<int,std::pair<int,int>> held; // flit -> destination, VC
    std::vector<std::deque<int>> returns;
    std::vector<json> progress;

    bool _EndpointCanInject(Flit const *f) override {
        return !streaming || sent.at(f->mid) < supplied.at(f->mid);
    }
    void _EndpointInjected(Flit const *f) override {
        if (!streaming) return;
        int ordinal=sent.at(f->mid)++;
        ordinals[f->id]=ordinal;
        progress.push_back({{"event","inject"},{"id",f->mid},{"flit",f->id},
            {"ordinal",ordinal},{"cycle",_time+1},{"source",f->src}});
    }
    void _EndpointCredit(Flit const *f, int subnet, int node) override {
        if (!enabled || !bounded) { TrafficManager::_EndpointCredit(f,subnet,node); return; }
        if (held.count(f->id)) throw std::runtime_error("Repeated held endpoint credit");
        held[f->id]={node,f->vc};
        int occupied=0;
        for (const auto &item:held) if (item.second.first==node) ++occupied;
        if (occupied>slots) throw std::runtime_error("Endpoint receive slots exceeded");
    }
    void _RetireFlit(Flit *f,int node) override {
        int mid=f->mid, fid=f->id;
        OnlineTrafficManager::_RetireFlit(f,node);
        if (!streaming) return;
        auto event=message_flits.at(mid).back();
        event["ordinal"]=ordinals.at(fid);
        progress.push_back({{"event","receive"},{"id",mid},{"flit",fid},
            {"ordinal",ordinals.at(fid)},{"cycle",_time+1},{"destination",node},{"record",event}});
        ordinals.erase(fid);
    }
    void ReturnCredits() {
        for (int node=0;node<_nodes;++node) if (!returns[node].empty()) {
            Credit *c=Credit::New(); c->AddVC(returns[node].front());
            returns[node].pop_front(); _net[0]->WriteCredit(c,node);
        }
    }
    void Step() override { ReturnCredits(); OnlineTrafficManager::Step(); }
public:
    BoundaryTrafficManager(const BookSimConfig &config,const std::vector<Network*> &net)
        : OnlineTrafficManager(config,net), original(config), returns(_nodes) {}
    bool Idle() const override {
        if (!held.empty()) return false;
        for (const auto &q:returns) if (!q.empty()) return false;
        return OnlineTrafficManager::Idle();
    }
    json Submit(const json &r) override {
        auto reply=OnlineTrafficManager::Submit(r);
        supplied.push_back(streaming?0:r.at("flits").get<int>()); sent.push_back(0);
        return reply;
    }
    json BoundaryCommand(const json &r) {
        std::string command=r.at("command");
        if (r.at("cycle").get<int>()!=_time) throw std::runtime_error("Endpoint clock mismatch");
        if (command=="boundary") {
            if (_time!=0 || rc_trace_instructions || enabled || _vcs!=1 ||
                original.GetStr("buffer_policy")!="private")
                throw std::runtime_error("Boundary mode requires empty one-VC private-buffer trace");
            slots=r.at("rx_slots"); bounded=r.at("bounded");
            streaming=r.at("streaming");
            if (bounded && !streaming) throw std::runtime_error("Bounded endpoint needs progress callbacks");
            if (slots<=0) throw std::runtime_error("Invalid receive slots");
            BookSimConfig sink(original);sink.Assign("vc_buf_size",slots);sink.Assign("buf_size",-1);
            for (auto *ch:_net[0]->GetEject()) {
                auto *router=dynamic_cast<IQRouter*>(ch->GetSource());
                if (!router) throw std::runtime_error("Endpoint requires IQRouter");
                router->ConfigureEndpointSink(sink,ch->GetSourcePort());
            }
            enabled=true;
        } else if (command=="supply") {
            int mid=r.at("id"),count=r.at("flits");
            if (!enabled || mid<0 || mid>=static_cast<int>(supplied.size()) ||
                count<=0 || supplied[mid]+count>msg_packets[mid])
                throw std::runtime_error("Invalid or excess supplied payload");
            supplied[mid]+=count;
        } else if (command=="commit") {
            int fid=r.at("flit");
            if (!enabled || !bounded || !held.count(fid)) throw std::runtime_error("Unknown committed flit");
            auto item=held.at(fid);held.erase(fid); returns[item.first].push_back(item.second);
        } else throw std::runtime_error("Unknown boundary command");
        return {{"ok",true},{"cycle",_time}};
    }
    json Advance(int limit) override {
        if (!enabled) return OnlineTrafficManager::Advance(limit);
        if (limit<_time || limit>1000000000) throw std::runtime_error("Invalid advance boundary");
        finished.clear();progress.clear();
        while (_time<limit) {
            if (Idle()) { skipped+=limit-_time;_time=limit;global_current_cycle=_time;break; }
            Step();
            if (!progress.empty() || !finished.empty()) break;
        }
        return {{"ok",true},{"cycle",_time},{"completed",finished},{"progress",progress},{"idle",Idle()}};
    }
};
