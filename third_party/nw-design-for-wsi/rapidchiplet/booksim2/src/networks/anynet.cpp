// $Id$

/*
 Copyright (c) 2007-2015, Trustees of The Leland Stanford Junior University
 All rights reserved.

 Redistribution and use in source and binary forms, with or without
 modification, are permitted provided that the following conditions are met:

 Redistributions of source code must retain the above copyright notice, this 
 list of conditions and the following disclaimer.
 Redistributions in binary form must reproduce the above copyright notice, this
 list of conditions and the following disclaimer in the documentation and/or
 other materials provided with the distribution.

 THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
 ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE 
 DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
 ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
 (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
 LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
 ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
 SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/

/*anynet
 *
 *Network setup file format
 *example 1:
 *router 0 router 1 15 router 2
 *
 *Router 0 is connect to router 1 with a 15-cycle channel, and router 0 is connected to
 * router 2 with a 1-cycle channel, the channels latency are unidirectional, so channel 
 * from router 1 back to router 0 is only single-cycle because it was not specified
 *
 *example 2:
 *router 0 node 0 node 1 5 node 2 5
 *
 *Router 0 is directly connected to node 0-2. Channel latency is 5cycles for 1 and 2. In 
 * this case the latency specification is bidirectional, the injeciton and ejection lat
 * for node 1 and 2 are 5-cycle
 *
 *other notes:
 *
 *Router and node numbers must be sequential starting with 0
 *Credit channel latency follows the channel latency, even though it travels in revse
 * direction this might not be desired
 *
 */


/* Documentation added by us
 
  	How the AnyNet topology file is parsed
	- The list must start with a router, not with a node (otherwise can't parse it)
	- Only router-to-router links can have custom latencies, node-to-router links are assumed to have latency 1 
	- Router-IDs and Node-IDs must be numbered starting from 0 and be sequential (i.e., 0,1,2,...N)
	- It is allowed to have some links with custom latencies and some without
	- The order of lines (router IDs) in the file does not matter
	- It is allowed to have routers without nodes before routers with nodes (and vice versa)
	- For a link A->B, the reverse link B->A is automatically created, but the latency only applies to A->B (B->A defaults to 1)
	- Duplicated links between two routers are ignored, the last latency specified is used (or 1 if none specified in the last link)

	node_list: map<int,int>
	node_list[node_id] = router_id
	Maps the node ID to the router ID it is connected to

	The router_list is only used in the AnyNet class and in custom classes, therefore, we modify it without braking BoookSim.
	router_list: vector<map<int,map<int,tuple<int,int,int>>>>
	router_list[0] is for node to router connections
		-> router_list[0][router_id][node_id] = (output_port_at_router, input_port_at_router, latency)
	router_list[1] is for router to router connections
		-> router_list[1][src_router_id][dst_router_id] = (output_port_at_src_router, input_port_at_dst_router, latency)

	_size: number of routers
	_nodes: number of nodes

	routing_table: vector<map<int,int>>
	routing_table[router_id][dest_node] = out_port
*/

#include "anynet.hpp"
#include <fstream>
#include <sstream>
#include <limits>
#include <algorithm>

// NOTE: Custom include
#include "ChannelDependencyGraph.hpp"
#include "shortest_path_lowest_id_first_routing.hpp"
#include "simple_cycle_breaking_set_routing.hpp"
#include "xy_routing.hpp"
#include "random_selection.hpp"
#include "balancing_selection.hpp"
#include "adaptive_selection.hpp"
#include <memory>                                  

// NOTE: Custom variables
std::unique_ptr<routing_function> modular_routing_function;
std::unique_ptr<selection_function> modular_selection_function;
std::vector<std::map<int,std::map<int,std::tuple<int,int,int>>>> global_router_list;
std::map<int,int> global_node_list;
std::vector<Router*>* global_router_object_list;

//this is a hack, I can't easily get the routing talbe out of the network
map<int, int>* global_routing_table;

// Constructor
AnyNet::AnyNet( const Configuration &config, const string & name ) :    Network( config, name ){
    router_list.resize(2);
    _ComputeSize( config );
    _Alloc( );
    _BuildNet( config );
	path_for_stats = config.GetStr("path_for_stats");

	// Hack to have node list and router list globally available
	global_router_list = router_list;
	global_node_list = node_list;
	global_router_object_list = &_routers;

	// Instantiate the routing function
	string rf_name = config.GetStr("modular_routing_function");
	if (rf_name == "shortest_path_lowest_id_first") {
		modular_routing_function = std::make_unique<shortest_path_lowest_id_first_routing>();
	} else if (rf_name == "simple_cycle_breaking_set") {
		modular_routing_function = std::make_unique<simple_cycle_breaking_set_routing>();
	} else if (rf_name == "xy") {
		modular_routing_function = std::make_unique<xy_routing>(config, global_node_list);
	} else {
		cout << "Error: The modular routing function " << rf_name << " is not supported in AnyNet" << endl;
		exit(-1);
	}
	// Instantiate the selection function
	string sf_name = config.GetStr("modular_selection_function");
	if (sf_name == "random") {
		modular_selection_function = std::make_unique<random_selection>();
	} else if (sf_name == "balancing") {
		modular_selection_function = std::make_unique<balancing_selection>();
	} else if (sf_name == "adaptive") {
		modular_selection_function = std::make_unique<adaptive_selection>(global_router_object_list);
	} else {
		cout << "Error: The modular selection function " << sf_name << " is not supported in AnyNet" << endl;
		exit(-1);
	}
	// NOTE: Custom code here
	// Check that the channel dependency graph is acyclic. Only for testing, remove for production 
	/*
	int n_routers = router_list[1].size();
	int n_nodes = node_list.size();
	int n_vcs = gNumVCs;
	ChannelDependencyGraph cdg(node_list, router_list, n_routers, n_nodes, n_vcs, *modular_routing_function);
	std::cout << "CDG CHECK: Channel dependency graph is " << (cdg.is_acyclic() ? "acyclic" : "cyclic (ERROR)") << std::endl;
	*/
}

// Destructor
AnyNet::~AnyNet(){
	// Report link usage statistics
	std::ofstream ofs(path_for_stats);  // open file for writing
	if (!ofs) {
		std::cerr << "Error: could not open link_usage_stats.txt for writing\n";
	} else {
		ofs << "src_router_id,dst_router_id,packet_count\n";
		for (std::map<std::pair<int,int>, int>::const_iterator it = packets_per_link.begin();
			 it != packets_per_link.end(); ++it)
		{
			const std::pair<int,int>& link = it->first;
			int count = it->second;
			ofs << link.first << "," << link.second << "," << count << "\n";
		}
		ofs.close();
	}
	// Free memory
    for(int i = 0; i < 2; ++i) {
        for(map<int, map<int, tuple<int,int,int> > >::iterator iter = router_list[i].begin(); iter != router_list[i].end(); ++iter) {
            iter->second.clear();
        }
    }
}


void AnyNet::_ComputeSize( const Configuration &config ){
	// Check if anynet topology file name is given
    file_name = config.GetStr("network_file");
    if(file_name==""){
        cout<<"No network file name provided"<<endl;
        exit(-1);
    }
    //parse the network description file
    readFile();

    _channels =0;
    cout<<"========================Network File Parsed=================\n";
	// Report nodes and what router they connect to
    cout<<"******************node listing**********************\n";
    map<int,    int >::iterator iter;
    for(iter = node_list.begin(); iter!=node_list.end(); iter++){
        cout<<"Node "<<iter->first;
        cout<<"\tRouter "<<iter->second<<endl;
    }

	// Report routers and what nodes they connect to
    map<int,     map<int, tuple<int,int,int> > >::iterator iter3;
    cout<<"\n****************router to node listing*************\n";
    for(iter3 = router_list[0].begin(); iter3!=router_list[0].end(); iter3++){
        cout<<"Router "<<iter3->first<<endl;
        map<int, tuple<int,int,int> >::iterator iter2;
        for(iter2 = iter3->second.begin(); 
	iter2!=iter3->second.end(); 
	iter2++){
            cout<<"\t Node "<<iter2->first<<" lat "<<get<2>(iter2->second)<<endl;
        }
    }

	// Report router-to-router connections to user
    cout<<"\n*****************router to router listing************\n";
    for(iter3 = router_list[1].begin(); iter3!=router_list[1].end(); iter3++){
        cout<<"Router "<<iter3->first<<endl;
        map<int, tuple<int,int,int> >::iterator iter2;
        if(iter3->second.size() == 0){
            cout<<"Caution Router "<<iter3->first
	    <<" is not connected to any other Router\n"<<endl;
        }
        for(iter2 = iter3->second.begin(); 
	iter2!=iter3->second.end(); 
	iter2++){
            cout<<"\t Router "<<iter2->first<<" lat "<< get<2>(iter2->second)<<endl;
            _channels++;
        }
    }

    _size = router_list[1].size();
    _nodes = node_list.size();

}


// Builds the network (routers, channels, etc.).
// Sets the output ports for the router-to-node links and router-to-router links in router_list
// Calls the function to build the routing table
void AnyNet::_BuildNet( const Configuration &config ){
    

    //I need to keep track the output ports for each router during build
	// One int per router
    int * outport = (int*)malloc(sizeof(int)*_size);
    for(int i = 0; i<_size; i++){outport[i] = 0;}
	// NOTE: Tracking of input channels added by us
	int * inport = (int*)malloc(sizeof(int)*_size);
	for(int i = 0; i<_size; i++){inport[i] = 0;}

    cout<<"==========================Node to Router =====================\n";
    //adding the injection/ejection chanenls first
    map<int,     map<int,tuple<int,int,int> > >::iterator niter;
    for(niter = router_list[0].begin(); niter!=router_list[0].end(); niter++){
        map<int,     map<int, tuple<int,int,int> > >::iterator riter = router_list[1].find(niter->first);
        //calculate radix
        int radix = niter->second.size()+riter->second.size();
        int node = niter->first;
        cout<<"router "<<node<<" radix "<<radix<<endl;
        //decalre the routers 
        ostringstream router_name;
        router_name << "router";
        router_name << "_" <<    node ;
        _routers[node] = Router::NewRouter( config, this, router_name.str( ), 
        					node, radix, radix );
        _timed_modules.push_back(_routers[node]);
        //add injeciton ejection channels
        map<int, tuple<int,int,int> >::iterator nniter;
        for(nniter = niter->second.begin();nniter!=niter->second.end(); nniter++){
            int link = nniter->first;
            //add the outport port assined to the map
			get<0>((niter->second)[link]) = outport[node];
			get<1>((niter->second)[link]) = inport[node];
			// Store also the reverse direction in the map: Here, we store -1 to easily identify links to NODEs rather than to ROUTERs
			router_and_outport_to_next_router[node][outport[node]] = -1;
            outport[node]++;
			inport[node]++;
            cout<<"\t connected to node "<<link<<" at outport "<< get<0>(nniter->second)
	    <<" lat "<<get<2>(nniter->second)<<endl;
			_inject[link]->SetLatency(get<2>(nniter->second));
			_inject_cred[link]->SetLatency(get<2>(nniter->second));
			_eject[link]->SetLatency(get<2>(nniter->second));
			_eject_cred[link]->SetLatency(get<2>(nniter->second));
			// Add Input and Output channels to the router
            _routers[node]->AddInputChannel( _inject[link], _inject_cred[link] );
            _routers[node]->AddOutputChannel( _eject[link], _eject_cred[link] );
        }

    }

    cout<<"==========================Router to Router =====================\n";
    //add inter router channels
    //since there is no way to systematically number the channels we just start from 0
    //the map, is a mapping of output->input
    int channel_count = 0; 
    for(niter = router_list[0].begin(); niter!=router_list[0].end(); niter++){
        map<int,     map<int, tuple<int,int,int> > >::iterator riter = router_list[1].find(niter->first);
        int node = niter->first;
        map<int, tuple<int,int,int> >::iterator rriter;
        cout<<"router "<<node<<endl;
        for(rriter = riter->second.begin();rriter!=riter->second.end(); rriter++){
            int other_node = rriter->first;
            int link = channel_count;
            //add the outport port assined to the map
			get<0>((riter->second)[other_node]) = outport[node];
			get<1>((riter->second)[other_node]) = inport[other_node];
			// Store also the reverse direction in the map
			router_and_outport_to_next_router[node][outport[node]] = other_node;
			// Increment next port ids
            outport[node]++;
			inport[other_node]++;
            cout<<"\t connected to router "<<other_node<<" using link "<<link
	    <<" at outport "<< get<0>(rriter->second)
	    <<" lat "<<get<2>(rriter->second)<<endl;

            _chan[link]->SetLatency(get<2>(rriter->second));
            _chan_cred[link]->SetLatency(get<2>(rriter->second));
			// Add Input and Output channels to the routers
            _routers[node]->AddOutputChannel( _chan[link], _chan_cred[link] );
            _routers[other_node]->AddInputChannel( _chan[link], _chan_cred[link]);
            channel_count++;
        }
    }

	// NOTE: With our modular routing, we don't need the default routing table since each routing function computes its own routing table
    // buildRoutingTable();

}


// Register routing functions with the routing function map
void AnyNet::RegisterRoutingFunctions() {
    gRoutingFunctionMap["modular_routing_anynet"] = &modular_routing_anynet;
}

void modular_routing_anynet(const Router *r, const Flit *f, int in_channel, OutputSet *outputs, bool inject ){
	// Number of VCs
	int n_vcs = gNumVCs;
	// Outputs of the routing function = inputs to the selection function
	vector<tuple<int, int, int>> valid_next_hops;
	// Outputs of the selection function
	tuple<int, int, int> next_hop;
	// Handle the injection case
	if (inject) {
		next_hop = make_tuple(-1, 0, n_vcs - 1);
	}else {
		// Inputs to the routing function
		int n_routers = global_router_list[1].size();
		int n_nodes = global_node_list.size();
		int cur_rid = r->GetID();
		int dst_nid = f->dest;
		int in_port = in_channel;
		int flit_id = f->id;
		// Call the modular routing function to get the valid next hops
		valid_next_hops = modular_routing_function->route(global_router_list, n_routers, n_nodes, n_vcs, cur_rid, dst_nid, in_port, flit_id);
		// Call the modular selection function to select one of the valid next hops
		next_hop = modular_selection_function->select(cur_rid, valid_next_hops);
		// Collect statistics for the number of packets per link
		int out_port = get<0>(next_hop);
		if (router_and_outport_to_next_router.find(cur_rid) == router_and_outport_to_next_router.end()) {
			cout << "Error: Router ID " << cur_rid << " not found in router_and_outport_to_next_router" << endl;
			exit(-1);
		}
		if (router_and_outport_to_next_router[cur_rid].find(out_port) == router_and_outport_to_next_router[cur_rid].end()) {
			cout << "Error: Output port " << out_port << " not found for router ID " << cur_rid << " in router_and_outport_to_next_router" << endl;
			exit(-1);
		}
		if (router_and_outport_to_next_router[cur_rid][out_port] == -1) {
			// Link to a node
			// Do nothing
		} else {
			// Link to a router
			int next_rid = router_and_outport_to_next_router[cur_rid][out_port];
			std::pair<int, int> link = std::make_pair(cur_rid, next_rid);
			if (packets_per_link.find(link) == packets_per_link.end()) {
				packets_per_link[link] = 0;
			}
			packets_per_link[link]++;
		}
	}
	// Set output port and VCs
	outputs->Clear();
	outputs->AddRange(get<0>(next_hop), get<1>(next_hop), get<2>(next_hop));
}

// Minimal routing function for AnyNet
// NOTE: With our modular routing, this function is not used anymore
void min_anynet( const Router *r, const Flit *f, int in_channel, OutputSet *outputs, bool inject ){
    int out_port=-1;
    if(!inject){
        assert(global_routing_table[r->GetID()].count(f->dest)!=0);
        out_port=global_routing_table[r->GetID()][f->dest];
    }
 

    int vcBegin = 0, vcEnd = gNumVCs-1;
    if ( f->type == Flit::READ_REQUEST ) {
        vcBegin = gReadReqBeginVC;
        vcEnd     = gReadReqEndVC;
    } else if ( f->type == Flit::WRITE_REQUEST ) {
        vcBegin = gWriteReqBeginVC;
        vcEnd     = gWriteReqEndVC;
    } else if ( f->type ==    Flit::READ_REPLY ) {
        vcBegin = gReadReplyBeginVC;
        vcEnd     = gReadReplyEndVC;
    } else if ( f->type ==    Flit::WRITE_REPLY ) {
        vcBegin = gWriteReplyBeginVC;
        vcEnd     = gWriteReplyEndVC;
    }

    outputs->Clear( );

    outputs->AddRange( out_port , vcBegin, vcEnd );
}

// Calls Dijkstra for each source router.
void AnyNet::buildRoutingTable(){
    cout<<"========================== Routing table    =====================\n";    
    routing_table.resize(_size);
    for(int i = 0; i<_size; i++){
        route(i);
    }
    global_routing_table = &routing_table[0];
}


//11/7/2012
//basically djistra's, tested on a large dragonfly anynet configuration
void AnyNet::route(int r_start){
    int* dist = new int[_size];
    int* prev = new int[_size];
    set<int> rlist;
    for(int i = 0; i<_size; i++){
        dist[i] =    numeric_limits<int>::max();
        prev[i] = -1;
        rlist.insert(i);
    }
    dist[r_start] = 0;
    while(!rlist.empty()){
        //find min 
        int min_dist = numeric_limits<int>::max();
        int min_cand = -1;
        for(set<int>::iterator i = rlist.begin();
	i!=rlist.end();
	i++){
            if(dist[*i]<min_dist){
	min_dist = dist[*i];
	min_cand = *i;
            }
        }
        rlist.erase(min_cand);

        //neighbor
        for(map<int,tuple<int,int,int> >::iterator i = router_list[1][min_cand].begin(); 
	i!=router_list[1][min_cand].end(); 
	i++){
            int new_dist = dist[min_cand] + get<2>(i->second);//distance is hops not cycles
            if(new_dist < dist[i->first]){
	dist[i->first] = new_dist;
	prev[i->first] = min_cand;
            }
        }
    }
    
    //post process from the prev list
    for(int i = 0; i<_size; i++){
        if(prev[i] ==-1){ //self
            assert(i == r_start);

            for(map<int, tuple<int, int, int> >::iterator iter = router_list[0][i].begin();
	    iter!=router_list[0][i].end();
	    iter++){
	routing_table[r_start][iter->first]=get<0>(iter->second);
	//cout<<"node "<<iter->first<<" port "<< iter->second.first<<endl;
            }
        } else {
            int distance=0;
            int neighbor=i;
            while(prev[neighbor]!=r_start){
	assert(router_list[1][neighbor].count(prev[neighbor])>0);
	distance+=get<2>(router_list[1][prev[neighbor]][neighbor]);//REVERSE lat
	neighbor= prev[neighbor];
            }
            distance+=get<2>(router_list[1][prev[neighbor]][neighbor]);//lat

            assert( router_list[1][r_start].count(neighbor)!=0);
            int port = get<0>(router_list[1][r_start][neighbor]);
            for(map<int, tuple<int,int,int> >::iterator iter = router_list[0][i].begin();
	    iter!=router_list[0][i].end();
	    iter++){
	routing_table[r_start][iter->first]=port;
	//cout<<"node "<<iter->first<<" port "<< port<<" dist "<<distance<<endl;
            }
        }
    }
}

// Reads the anynet topology from a file and stores the information in node_list and router_list
// Does set the link latencies but does not set the output ports (done in _BuildNet)
void AnyNet::readFile(){
    ifstream network_list;
    string line;
    enum ParseState{HEAD_TYPE=0,
		    HEAD_ID,
		    BODY_TYPE, 
		    BODY_ID,
		    LINK_WEIGHT};

    enum ParseType{NODE=0,
		 ROUTER,
		 UNKNOWN};

    network_list.open(file_name.c_str());
    if(!network_list.is_open()){
        cout<<"Anynet:can't open network file "<<file_name<<endl;
        exit(-1);
    }
    
    //loop through the entire file
    while(!network_list.eof()){
        getline(network_list,line);
        if(line==""){
            continue;
        }

        ParseState state=HEAD_TYPE;
        //position to parse out white sspace
        int pos = 0;
        int next_pos=-1;
        string temp;
        //the first node and its type
        int head_id = -1;
        ParseType head_type = UNKNOWN;
        //stuff that head are linked to
        ParseType body_type = UNKNOWN;
        int body_id = -1;
        int link_weight = 1;
        do{
            //skip empty spaces
            next_pos = line.find(" ",pos);
            temp = line.substr(pos,next_pos-pos);
            pos = next_pos+1;
            if(temp=="" || temp==" "){
				continue;
            }

            switch(state){
			// Identify the first item in the line (if this is not router, parsing fails)
            case HEAD_TYPE:
				if(temp=="router"){
					head_type = ROUTER;
				} else if (temp == "node"){
					head_type = NODE;
				} else {
					cout<<"Anynet:Unknow head of line type "<<temp<<"\n";
					assert(false);
				}
				state=HEAD_ID;
				break;
			// Identify the ID of the first item in the line (must be a router)
			case HEAD_ID:
				//need better error check
				head_id = atoi(temp.c_str());
				//intialize router structures
				if(router_list[NODE].count(head_id) == 0){
					router_list[NODE][head_id] = map<int, tuple<int,int,int> >();
				}
				if(router_list[ROUTER].count(head_id) == 0){
					router_list[ROUTER][head_id] = map<int, tuple<int,int,int> >();
				}    
				state=BODY_TYPE;
				break;
			// Try to read link latency (only for router-to-router links and only if present in the file)
			case LINK_WEIGHT:
				if(temp=="router"|| temp == "node"){
					//ignore
				} else {
					link_weight= atoi(temp.c_str());
					// NOTE: We added the feature of custom link latencies for router-to-node links (only worked for router-to-router links before)
					if(body_type == ROUTER){
						get<2>(router_list[ROUTER][head_id][body_id])=link_weight;
					}
					else if (body_type == NODE){
						get<2>(router_list[NODE][head_id][body_id])=link_weight;
					}
					break;
				}
				//intentionally letting it flow through
			// Identify the type of the next item in the line (can be router or node)
			case BODY_TYPE:
				if(temp=="router"){
					body_type = ROUTER;
				} else if (temp == "node"){
					body_type = NODE;
				} else {
					cout<<"Anynet:Unknow body type "<<temp<<"\n";
					assert(false);
				}
				state=BODY_ID;
				break;
			// Identify the ID of the next item in the line (can be router or node)
			case BODY_ID:
				body_id = atoi(temp.c_str());	
				//intialize router structures if necessary
				if(body_type==ROUTER){
					if(router_list[NODE].count(body_id) ==0){
						router_list[NODE][body_id] = map<int, tuple<int,int,int> >();
					}
					if(router_list[ROUTER].count(body_id) == 0){
						router_list[ROUTER][body_id] = map<int, tuple<int,int,int> >();
					}
				}
				// Node-Node -> not allowed
				if(head_type==NODE && body_type==NODE){ 

					cout<<"Anynet:Cannot connect node to node "<<temp<<"\n";
					assert(false);
				// Node-Router -> does not work properly
				} else if(head_type==NODE && body_type==ROUTER){

					if(node_list.count(head_id)!=0 &&
						 node_list[head_id]!=body_id){
						cout<<"Anynet:Node "<<body_id<<" trying to connect to multiple router "
					<<body_id<<" and "<<node_list[head_id]<<endl;
						assert(false);
					}
					node_list[head_id]=body_id;
					router_list[NODE][body_id][head_id]=tuple<int, int, int>(-1,-1,1);
				// Router-Node -> works properly
				} else if(head_type==ROUTER && body_type==NODE){
					//insert and check node
					if(node_list.count(body_id) != 0 &&
						 node_list[body_id]!=head_id){
						cout<<"Anynet:Node "<<body_id<<" trying to connect to multiple router "
					<<body_id<<" and "<<node_list[head_id]<<endl;
						assert(false);
					}
					node_list[body_id] = head_id;
					router_list[NODE][head_id][body_id]=tuple<int, int, int>(-1,-1,1);
				// Router-Router -> works properly	
				} else if(head_type==ROUTER && body_type==ROUTER){
					router_list[ROUTER][head_id][body_id]=tuple<int, int, int>(-1,-1,1);
					if(router_list[ROUTER][body_id].count(head_id)==0){
						router_list[ROUTER][body_id][head_id]=tuple<int, int, int>(-1,-1,1);
					}
				}
				// Only for router-to-router links: try to read a link latency
				state=LINK_WEIGHT;
				break ;
			default:
				cout<<"Anynet:Unknow parse state\n";
				assert(false);
				break;
			}
        } while(pos!=0);
        if(state!=LINK_WEIGHT &&
             state!=BODY_TYPE){
            cout<<"Anynet:Incomplete parse of the line: "<<line<<endl;
        }

    }

    //map verification, make sure the information contained in both maps
    //are the same
    assert(router_list[0].size() == router_list[1].size());

    //traffic generator assumes node list is sequential and starts at 0
    vector<int> node_check;
    for(map<int,int>::iterator i = node_list.begin(); i!=node_list.end(); i++){
        node_check.push_back(i->first);
    }
    sort(node_check.begin(), node_check.end());
    for(size_t i = 0; i<node_check.size(); i++){
        if((size_t)node_check[i] != i){
            cout<<"Anynet:booksim trafficmanager assumes sequential node numbering starting at 0\n";
            assert(false);
        }
    } 
}

