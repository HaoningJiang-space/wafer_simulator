# Python modules
from typing import Dict, Tuple


# Custom modules
import config as cfg
import helpers as hlp
from System import System

def compute_link_power(throughput : float, zero_latency_avg : float, hops_avg : float, n_compute_reticles : int, technology : str) -> float:
    # We estimate the avg physical distance traveled by a flit by subtracting the router latency from the zero-load latency
    distance_avg = (zero_latency_avg - (hops_avg * cfg.router_latency_cycles)) * cfg.signal_propagation_per_cycle_mm    # in mm 
    # Compute the size of a flit
    flit_size = cfg.link_bandwidth_bit_per_sec / cfg.network_frequency_hz                                               # in bits
    # Get energy per bit per mm based on the technology node
    energy_per_bit_per_mm_in_pj = 0.0
    if technology == "45nm":
        energy_per_bit_per_mm_in_pj = cfg.energy_per_bit_per_mm_45nm_in_pj
    elif technology == "7nm":
        energy_per_bit_per_mm_in_pj = cfg.energy_per_bit_per_mm_7nm_in_pj
    else:
        hlp.register_error(f"Unsupported technology node: {technology}. Supported nodes are '45nm' and '7nm'.")
    # We compute the total energy that is needed to move one flit from source to destination
    energy_per_flit = distance_avg * flit_size * energy_per_bit_per_mm_in_pj                                            # in pJ/flit
    # The load represents the number of injected flits per gpc per cycle. We use it to compute the total number of injected flits per cycle at the given throughput
    injected_flits_per_cycle = throughput * n_compute_reticles * cfg.number_of_gpcs                                     # in flits/cycle       
    # We compute the energy per cycle based on the total energy per flit and the number of injected flits per cycle
    # This is an amortized analysis as each flit consumes its energy over multiple cycles, but there are also new flits injected in each cycle 
    # This amortization holds because all data we use from the booksim simulations are averaged over the whole simulation time
    energy_per_cycle = energy_per_flit * injected_flits_per_cycle                                                       # in pJ/cycle
    # We compute the power based on the energy per cycle and the network frequency
    Plink = energy_per_cycle * cfg.network_frequency_hz * 1e-9                                                          # in mW (same as Orion results) (*1e-9 for pJ to mW)
    return Plink 


# Note: The link power is compute at saturation throughput
def add_power_summary(results : Dict) -> None:
    # Check that the topology analysis results are present
    if "topology_analysis" not in results:
        hlp.register_error("Topology analysis results not found in the results dictionary. Run topology analysis before computing power summary.")
    # Check that the orion results are present
    if "orion3" not in results:
        hlp.register_error("Orion3 results not found in the results dictionary. Run Orion3 before computing power summary.")
    # Check that booksim results are present
    if "rapidchiplet" not in results or "booksim_simulation" not in results["rapidchiplet"]:
        hlp.register_error("Booksim results not found in the results dictionary. Run Booksim before computing power summary.")
    # Identify the orion results for compute and interconnect reticles
    n_compute_reticles = results["topology_analysis"]["n_compute_reticles"]
    orion_res_comp = {}
    n_interconnect_reticles = results["topology_analysis"]["n_interconnect_reticles"]
    if n_compute_reticles > 0:
        keys = [key for key in results["orion3"] if key.startswith("compute-reticle")]
        if len(keys) == 0:
            hlp.register_error("No compute reticle found in the Orion3 results.")
        elif len(keys) == 1:
            orion_res_comp = results["orion3"][keys[0]]
        else:
            hlp.register_error("Multiple compute reticles found in the Orion3 results. Please ensure that all compute reticles have the same radix.")
    orion_res_inter = {}
    if n_interconnect_reticles > 0:
        keys = [key for key in results["orion3"] if key.startswith("interconnect-reticle")]
        if len(keys) == 0:
            hlp.register_error("No interconnect reticle found in the Orion3 results.")
        elif len(keys) == 1:
            orion_res_inter = results["orion3"][keys[0]]
        else:
            hlp.register_error("Multiple interconnect reticles found in the Orion3 results. Please ensure that all interconnect reticles have the same radix.")
    # Compute the power summary (power of the whole system) based on the orion results. Unfortunately, Orion does only support 45nm technology node and older
    # All power results are in mW
    power_summary_45nm = {"Pleakage" : 0.0, "Pinternal" : 0.0, "Pswitching" : 0.0, "Ptotal" : 0.0, "Plink" : 0.0}
    # Add the power of the compute reticles and interconnect reticles
    for key in power_summary_45nm:
        if n_compute_reticles > 0 and key in orion_res_comp:
            power_summary_45nm[key] += n_compute_reticles * orion_res_comp[key]
        if n_interconnect_reticles > 0 and key in orion_res_inter:
            power_summary_45nm[key] += n_interconnect_reticles * orion_res_inter[key]
    # For booksim, we perform multiple runs. Here, we identify the median run based on the saturation throughput
    saturation_throughputs = [results["rapidchiplet"]["booksim_simulation"][rep]["summary"]["saturation_throughput"] for rep in range(len(results["rapidchiplet"]["booksim_simulation"]))]
    sorted_data = sorted((value, index) for index, value in enumerate(saturation_throughputs))
    median_rep = sorted_data[len(sorted_data) // 2][1]
    booksim_res = results["rapidchiplet"]["booksim_simulation"][median_rep]
    # Identify the load at saturation throughput
    saturation_throughput = booksim_res["summary"]["saturation_throughput"]
    # We take the zero-load latency at the minimum load. This latency is assumed to be only link-latency + router-latency, but no queuing latency
    zero_latency_avg = booksim_res["summary"]["zero_load_latency"]                                                          # in cycles
    # We take the hops at saturation throughput. For non-adaptive routing, the hops are similar for all loads, for adaptive routing, hops can increase with higher load
    hops_avg = booksim_res["detailed"][str(saturation_throughput)]["hops"]["avg"]                                           # in hops
    power_summary_45nm["Plink"] = compute_link_power(saturation_throughput, zero_latency_avg, hops_avg, n_compute_reticles, "45nm")
    power_summary_45nm["Ptotal"] += power_summary_45nm["Plink"]
    # Compute the energy per flit to compare systems with different throughputs
    flit_size = cfg.link_bandwidth_bit_per_sec / cfg.network_frequency_hz                                       # in bits  
    flits_per_cycle = saturation_throughput * n_compute_reticles * cfg.number_of_gpcs                           # in flits/cycle 
    energy_per_second = power_summary_45nm["Ptotal"] * 1e9                                                      # in pJ/s (*1e9 for mW to pJ)
    energy_per_cycle = energy_per_second / cfg.network_frequency_hz                                             # in pJ/cycle
    energy_per_flit = energy_per_cycle / flits_per_cycle if flits_per_cycle > 0 else 0.0                        # in pJ/flit
    power_summary_45nm["energy_per_byte_in_pJ"] = energy_per_flit / (flit_size / 8) if flit_size > 0 else 0.0   # in pJ/byte
    results["power_summary_45nm"] = power_summary_45nm
    # Estimate a power summary for 7nm based on the 45nm results
    power_summary_7nm = {}
    power_summary_7nm["Pleakage"] = power_summary_45nm["Pleakage"] * cfg.power_scaling_factor_45nm_to_7nm
    power_summary_7nm["Pinternal"] = power_summary_45nm["Pinternal"] * cfg.power_scaling_factor_45nm_to_7nm
    power_summary_7nm["Pswitching"] = power_summary_45nm["Pswitching"] * cfg.power_scaling_factor_45nm_to_7nm
    power_summary_7nm["Plink"] = compute_link_power(saturation_throughput, zero_latency_avg, hops_avg, n_compute_reticles, "7nm")
    power_summary_7nm["Ptotal"] = sum(power_summary_7nm[key] for key in ["Pleakage", "Pinternal", "Pswitching", "Plink"])
    energy_per_second = power_summary_7nm["Ptotal"] * 1e9                                                       # in pJ/s (*1e9 for mW to pJ)
    energy_per_cycle = energy_per_second / cfg.network_frequency_hz                                             # in pJ/cycle
    energy_per_flit = energy_per_cycle / flits_per_cycle if flits_per_cycle > 0 else 0.0                        # in pJ/flit
    power_summary_7nm["energy_per_byte_in_pJ"] = energy_per_flit / (flit_size / 8) if flit_size > 0 else 0.0    # in pJ/byte
    results["power_summary_7nm"] = power_summary_7nm

def add_area_summary(results : Dict, system : System) -> None:
    # Check that the topology analysis results are present
    if "topology_analysis" not in results:
        hlp.register_error("Topology analysis results not found in the results dictionary. Run topology analysis before computing area summary.")
    # Check that the orion results are present
    if "orion3" not in results:
        hlp.register_error("Orion3 results not found in the results dictionary. Run Orion3 before computing area summary.")
    # Identify the orion results for compute and interconnect reticles
    n_compute_reticles = results["topology_analysis"]["n_compute_reticles"]
    n_interconnect_reticles = results["topology_analysis"]["n_interconnect_reticles"]
    orion_res_comp = {}
    if n_compute_reticles > 0:
        keys = [key for key in results["orion3"] if key.startswith("compute-reticle")]
        if len(keys) == 0:
            hlp.register_error("No compute reticle found in the Orion3 results.")
        elif len(keys) == 1:
            orion_res_comp = results["orion3"][keys[0]]
        else:
            hlp.register_error("Multiple compute reticles found in the Orion3 results. Please ensure that all compute reticles have the same radix.")
    orion_res_inter = {}
    if n_interconnect_reticles > 0:
        keys = [key for key in results["orion3"] if key.startswith("interconnect-reticle")]
        if len(keys) == 0:
            hlp.register_error("No interconnect reticle found in the Orion3 results.")
        elif len(keys) == 1:
            orion_res_inter = results["orion3"][keys[0]]
        else:
            hlp.register_error("Multiple interconnect reticles found in the Orion3 results. Please ensure that all interconnect reticles have the same radix.")
    # Compute the area summary (area of the whole system) based on the orion results
    area_summary_45nm = {"Ainbuffer" : 0.0, "Aoutbuffer" : 0.0, "Acrossbar" : 0.0, "Aswvc" : 0.0, "Aclkctrl" : 0.0, "Atotal" : 0.0}
    for key in area_summary_45nm:
        if n_compute_reticles > 0:
            area_summary_45nm[key] += n_compute_reticles * orion_res_comp[key]
        if n_interconnect_reticles > 0:
            area_summary_45nm[key] += n_interconnect_reticles * orion_res_inter[key]
    # Add overall silicon area that was patterned and silicon area available for GPU logic
    A_silicon_compute_only = sum([ret.get_area() for wafer in system.wafers for ret in wafer.reticles if ret.typ == "compute"]) * 1e6    # mm^2 to um^2
    area_summary_45nm["Asilicon"] = sum([ret.get_area() for wafer in system.wafers for ret in wafer.reticles]) * 1e6    # mm^2 to um^2
    area_summary_45nm["Agpu"] = A_silicon_compute_only - area_summary_45nm["Atotal"]
    results["area_summary_45nm"] = area_summary_45nm
    # Estimate an area summary for 7nm based on the 45nm results
    area_summary_7nm = {}
    for metric, value in area_summary_45nm.items():
        area_summary_7nm[metric] = value * cfg.area_scaling_factor_45nm_to_7nm
    area_summary_7nm["Asilicon"] = sum([ret.get_area() for wafer in system.wafers for ret in wafer.reticles]) * 1e6     # mm^2 to um^2
    area_summary_7nm["Agpu"] = A_silicon_compute_only - area_summary_7nm["Atotal"]
    results["area_summary_7nm"] = area_summary_7nm
