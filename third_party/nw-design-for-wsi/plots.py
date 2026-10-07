# Python modules
import sys
import copy as cpy
import pandas as pd
import matplotlib
matplotlib.use("Agg") # Disable interactive mode but make thread-safe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Rectangle
from typing import Dict, List
import matplotlib.colors as mcolors
import math
import os

# Custom modules
import helpers as hlp
import config as cfg
from System import System
import analyze_topology as at
import run_experiment as run_exp
import power_and_area_summary as pas

label_map = {
        "shortest_path_lowest_id_first" : "SPLIF",
        "simple_cycle_breaking_set" : "SCBS",
        "random" : "Random",
        "balancing" : "Balancing",
        "adaptive" : "Adaptive",
        "baseline" : "Baseline",
        "ours_aligned" : "Ours Aligned",
        "ours_interleaved" : "Ours Interleaved",
        "ours_rotated" : "Ours Rotated",
        "ours_contoured" : "Ours Contoured",
        }

def read_all_results(experiment : Dict) -> Dict:
    results = {}
    # Go through all designs
    for traffic in experiment["traffic"]:
        results[traffic] = {}
        for integration_level in experiment["integration_level"]:
            results[traffic][integration_level] = {}
            for wafer_diameter in experiment["wafer_diameter"]:
                results[traffic][integration_level][wafer_diameter] = {}
                for wafer_utilization in experiment["wafer_utilization"]:
                    results[traffic][integration_level][wafer_diameter][wafer_utilization] = {}
                    for method in experiment["method"]:
                        results[traffic][integration_level][wafer_diameter][wafer_utilization][method] = {}
                        for routing_function in experiment["routing_function"]:
                            results[traffic][integration_level][wafer_diameter][wafer_utilization][method][routing_function] = {}
                            for selection_function in experiment["selection_function"]:
                                results[traffic][integration_level][wafer_diameter][wafer_utilization][method][routing_function][selection_function] = {}
                                filename = "%s_%dmm_%s_%s_%s_%s_%s_results.json" % (integration_level, wafer_diameter, wafer_utilization, method, routing_function, selection_function, traffic)
                                # Skip invalid combinations
                                if integration_level == "logic_and_logic" and method in ["ours_interleaved", "ours_rotated"]:
                                    continue
                                try:
                                    results[traffic][integration_level][wafer_diameter][wafer_utilization][method][routing_function][selection_function] = hlp.read_json("results/%s" % filename, suppress_errors=True)
                                    hlp.print_green("Successfully read results from file results/%s." % filename)
                                except:
                                    results[traffic][integration_level][wafer_diameter][wafer_utilization][method][routing_function][selection_function] = None
                                    hlp.print_yellow("Warning: Could not read results from file results/%s. Skipping this design." % filename)
    return results


# Two subplots:  Left: Area of compute reticle
#                Right: Area of interconnect reticle

def plot_area_analysis(results : Dict, name : str) -> None:
    # Check if all results have BookSim simulation data (inside the rapidchiplet section)
    if not all("area_summary_7nm" in results[m][rf][sf] for m in results for rf in results[m] for sf in results[m][rf] if results[m][rf][sf] is not None):
        hlp.register_error("Cannot area power analysis for %s because 7nm Area results are missing." % name)
    # Flat version of results
    results_flat = [results[m][rf][sf] for m in results for rf in results[m] for sf in results[m][rf] if results[m][rf][sf] is not None]
    if len(results_flat) == 0:
        print("Warning: No valid results found for plotting power analysis for %s." % name)
        return
    # Create the plot
    print(len(results))
    # This identifies logic_and_logic designs and makes the plot smaller
    if len(results) <= 2:
        # No interconnect reticle present -> Only one subplot
        fig, ax = plt.subplots(1,1,figsize=(2, 4))
        fig.subplots_adjust(left = 0.325, right = 0.675, top = 0.98, bottom = 0.02, wspace=3)
        ax = [ax]  
    else:
        fig, ax = plt.subplots(1,2,figsize=(5, 4))
        fig.subplots_adjust(left = 0.10, right = 0.88, top = 0.98, bottom = 0.02, wspace=1.0)

    area_reticle = cfg.parameters["reticle_size"][0] * cfg.parameters["reticle_size"][1] # in mm^2
    # Plot each method; routing function; selection function combination
    cnt = 0
    all_labs = []
    max_area_compute = 0.0
    max_area_intercon = 0.0
    for (i, m) in enumerate(results.keys()):
        if results[m] is None:
            continue
        rf = list(results[m].keys())[0]
        if results[m][rf] is None:
            continue
        sf = list(results[m][rf].keys())[0]
        if results[m][rf][sf] is None:
            continue
        # Collect data for compute reticle
        res = results[m][rf][sf]
        comp_keys = [key for key in res["orion3"] if key.startswith("compute")]
        if len(comp_keys) != 1:
            hlp.register_error("Expected exactly one compute reticle Orion result in design %s with method %s, routing function %s, selection function %s, but found %d." % (name, m, rf, sf, len(comp_keys)))
        comp_key = comp_keys[0]
        area_results_compute_45nm = {key : val * 1e-6 for (key,val) in res["orion3"][comp_key].items() if key.startswith("A") and key != "Atotal"}  # um^2 to mm^2
        area_results_compute_7nm = {key : val * (cfg.area_scaling_factor_45nm_to_7nm_sram if key == "Ainbuffer" else cfg.area_scaling_factor_45nm_to_7nm) for (key,val) in area_results_compute_45nm.items()}
        area_total = sum(area_results_compute_7nm.values())

        # Plot on stacked bar at x position cnt for compute reticle
        col = cfg.colors[(cnt * 2) % len(cfg.colors)]
        lab = "%s" % label_map[m]
        all_labs.append(lab)
        max_area_compute = max(max_area_compute, area_total)
        ax[0].bar(cnt, area_total, label = lab, color = col, zorder=3)

        # Interconnect reticle: Not present for logic_and_logic integration
        if res["topology_analysis"]["n_interconnect_reticles"] > 0:
            # Collect data for interconnect reticle
            intercon_keys = [key for key in res["orion3"] if key.startswith("interconnect")]
            if len(intercon_keys) != 1:
                hlp.register_error("Expected exactly one interconnect reticle Orion result in design %s with method %s, routing function %s, selection function %s, but found %d." % (name, m, rf, sf, len(intercon_keys)))
            intercon_key = intercon_keys[0]
            area_results_intercon_45nm = {key : val * 1e-6 for (key,val) in res["orion3"][intercon_key].items() if key.startswith("A") and key != "Atotal"}     # um^2 to mm^2
            area_results_intercon_7nm = {key : val * (cfg.area_scaling_factor_45nm_to_7nm_sram if key == "Ainbuffer" else cfg.area_scaling_factor_45nm_to_7nm) for (key,val) in area_results_intercon_45nm.items()}
            area_total = sum(area_results_intercon_7nm.values())

            # Plot on stacked bar at x position cnt for interconnect reticle
            max_area_intercon = max(max_area_intercon, area_total)
            ax[1].bar(cnt, area_total, label = lab, color = col, zorder=3)

            
        # Update counter (for colors and markers)
        cnt += 1

    # Add second axis showing the percentage of the reticle area occupied
    ax[0].set_ylim(0, max_area_compute * 1.1)
    ax[0].right_ax = ax[0].twinx()
    ax[0].right_ax.set_ylabel("Percentage of Reticle Area Occupied by Network [%]")
    ax[0].right_ax.set_ylim(0, max_area_compute / area_reticle * 110)
    ax[0].right_ax.grid(False)

    if len(ax) > 1:
        ax[1].set_ylim(0, max_area_intercon * 1.1)
        ax[1].right_ax = ax[1].twinx()
        ax[1].right_ax.set_ylabel("Percentage of Reticle Area Occupied by Network [%]")
        ax[1].right_ax.set_ylim(0, max_area_intercon / area_reticle * 110)
        ax[1].right_ax.grid(False)
        # Subplot 2: Interconnect reticle
        ax[1].set_ylabel(r"Total Area of Network in Interconnect Reticle [mm$^2$]")


    # Common settings for axis
    for i in range(len(ax)):
        # X-Axis
        ax[i].set_xticks(range(cnt))
        for (j, lab) in enumerate(all_labs):
            ax[i].text(j, 0, "  " + lab, rotation=90, va='bottom', ha='center', fontsize=9)
        # General
        ax[i].grid(axis='y', zorder=0)

    # Subplot 1: Compute reticle
    ax[0].set_ylabel(r"Total Area of Network in Compute Reticle [mm$^2$]")


    # Save the figure
    plt.savefig("plots/" + name + "_area_analysis." + cfg.plot_format, dpi=cfg.plot_dpi)
    plt.close(fig)


# Two subplots:  Left: Total power consumption at saturation throughput
#                Right: Energy per byte transferred (at saturation throughput)

def plot_power_analysis(results : Dict, name : str) -> None:
    # Check if all results have BookSim simulation data (inside the rapidchiplet section)
    if not all("power_summary_7nm" in results[m][rf][sf] for m in results for rf in results[m] for sf in results[m][rf] if results[m][rf][sf] is not None):
        hlp.register_error("Cannot plot power analysis for %s because 7nm Power results are missing." % name)
    # Flat version of results
    results_flat = [results[m][rf][sf] for m in results for rf in results[m] for sf in results[m][rf] if results[m][rf][sf] is not None]
    if len(results_flat) == 0:
        print("Warning: No valid results found for plotting power analysis for %s." % name)
        return
    # Create the plot
    if len(results) <= 2:
        fig, ax = plt.subplots(1,2,figsize=(3.5, 4))
        fig.subplots_adjust(left = 0.2, right = 0.98, top = 0.98, bottom = 0.02, wspace=0.7)
    else:
        fig, ax = plt.subplots(1,2,figsize=(5, 4))
        fig.subplots_adjust(left = 0.16, right = 0.99, top = 0.98, bottom = 0.02, wspace=0.375)

    # Plot each method; routing function; selection function combination
    cnt = 0
    all_labs = []
    for (i, m) in enumerate(results.keys()):
        if results[m] is None:
            continue
        for (j, rf) in enumerate(results[m].keys()):
            if results[m][rf] is None:
                continue
            for (k, sf) in enumerate(results[m][rf].keys()):
                # Skip missing data
                if results[m][rf][sf] is None:
                    continue

                # Collect data
                res = results[m][rf][sf]
                p_tot = res["power_summary_7nm"]["Ptotal"] * 1e-3           # mW to W
                p_by_type = {typ : res["power_summary_7nm"][typ] * 1e-3 for typ in res["power_summary_7nm"] if typ.startswith("P") and typ != "Ptotal"}
                e_byte = res["power_summary_7nm"]["energy_per_byte_in_pJ"]    # in pJ/byte

                # Plot config 
                col = cfg.colors[cnt % len(cfg.colors)]
                lab = "%s (%s)" % (label_map[m], label_map[sf])
                all_labs.append(lab)

                # Subplot 1: Total Power Consumption 
                ax[0].bar(cnt, p_tot, label = lab, color = col, zorder=3)

                # Subplot 2: Energy per byte as bars at x position cnt
                ax[1].bar(cnt, e_byte, label = lab, color = col, zorder=3)

                # Update counter (for colors and markers)
                cnt += 1
    # Common settings for axis
    for i in range(2):
        # X-Axis
        ax[i].set_xticks(range(cnt))
        for (j, lab) in enumerate(all_labs):
            ax[i].text(j, 0, "  " + lab, rotation=90, va='bottom', ha='center', fontsize=9)
        # General
        ax[i].grid(axis='y', zorder=0)

    # Subplot 1: Total Power Consumption
    ax[0].set_ylabel("Network Power at Saturation Throughput [W]")

    # Subplot 2: Energy per byte
    ax[1].set_ylabel("Energy per Byte at Saturation Throughput [pJ/Byte]")

    # Save the figure
    plt.savefig("plots/" + name + "_power_analysis." + cfg.plot_format, dpi=cfg.plot_dpi)
    plt.close(fig)


def visualize_network_topology(system : System, name : str, do_shift : bool = False) -> None:
    # Check if all reticles have the neighbor attribute. If not add it.
    if not all("neighbors" in reticle.attributes for wafer in system.wafers for reticle in wafer.reticles):
        at.add_neighbor_information(system)
    # Create figure and axis
    fig, ax = plt.subplots(figsize=(10, 10))
    scale = max([coord for wafer in system.wafers for reticle in wafer.reticles for point in reticle.shape_points for coord in point]) / 50
    # Draw all links (edges in a graph)
    for (wid, wafer) in enumerate(system.wafers):
        for (rid, reticle) in enumerate(wafer.reticles):
            y = reticle.y + scale * 3 * do_shift * (wid - len(system.wafers)/2)
            for (owid, orid, ovcid, vcid) in reticle.attributes["neighbors"]:
                if owid < wid:
                    owafer = system.wafers[owid]
                    oreticle = owafer.reticles[orid]
                    oy = oreticle.y + scale * 3 * do_shift * (owid - len(system.wafers)/2)
                    ax.plot([reticle.x, oreticle.x], [y, oy], color='black', linewidth=scale, zorder=0)
    # Draw all reticles (nodes in a graph)
    for (wid, wafer) in enumerate(system.wafers):
        for (rid, reticle) in enumerate(wafer.reticles):
            col = cfg.reticle_color_by_layer[str((2 * wid) % len(cfg.reticle_color_by_layer))]
            y = reticle.y + scale * 3 * do_shift * (wid - len(system.wafers)/2)
            circ = Circle((reticle.x, y), radius=scale, color=col, zorder=1)
            ax.add_patch(circ)
    # Hide axes
    ax.set_xticks([])
    ax.set_yticks([])
    # Set aspect ratio to equal
    ax.set_aspect('equal')
    # Save the figure
    plt.savefig("plots/" + name + "_topology." + cfg.plot_format, dpi=cfg.plot_dpi)
    plt.close(fig)

# Deprecated: Might not work with the new result format
def plot_path_length_distribution(results : Dict, name : str) -> None:
    # This plot requires the topology analysis to have been run
    if not all("topology_analysis" in results[method] for method in results if results[method] is not None):
        hlp.register_error("Cannot plot path length distribution for %s because topology analysis results are missing." % name)
    # Compute diameter and check if any path lengths are odd
    max_diameter = max([results[method]["topology_analysis"]["diameter"] for method in results if results[method] is not None])
    has_odd_path_lengths = any(pl % 2 == 1 for method in results if results[method] is not None for pl in results[method]["topology_analysis"]["path_lengths"])
    # Create the plot
    bin_edges = np.arange(0, max_diameter + 3, 1 if has_odd_path_lengths else 2)  # bins of size 1 or 2
    bin_centers = np.array([x + (0.5 if has_odd_path_lengths else 1) for x in bin_edges[:-1]])
    n_datasets = len(results)   # number of methods
    bar_width = 0.8 * (1 if has_odd_path_lengths else 2) / n_datasets  # total group width = 0.8
    fig, ax = plt.subplots(figsize=(10, 6))
    for i, method in enumerate(results.keys()):
        if results[method] is None:
            continue
        path_lengths = results[method]["topology_analysis"]["path_lengths"]
        counts, _ = np.histogram(path_lengths, bins=bin_edges, density=True)
        ax.bar(bin_centers + i*bar_width - (0.4 if has_odd_path_lengths else 0.8) + bar_width/2,
               counts,
               width=bar_width,
               label=method,
               align='center',
               color=cfg.colors[i % len(cfg.colors)],
               )
    ax.set_xticks(bin_centers)
    ax.set_xticklabels([str(int(x)) for x in bin_centers])
    ax.set_xlabel("Path Length")
    # Y-Axis
    ax.set_ylabel("Density")
    # General
    ax.set_title("Path Length Distribution of %s" % name)
    ax.legend()
    plt.tight_layout()
    # Save the figure
    plt.savefig("plots/" + name + "_path_length_distribution." + cfg.plot_format, dpi=cfg.plot_dpi)
    plt.close(fig)

def plot_latency_vs_load(results : Dict, name : str) -> None:
    # Check if all results have BookSim simulation data (inside the rapidchiplet section)
    if not all("rapidchiplet" in results[m][rf][sf] for m in results for rf in results[m] for sf in results[m][rf] if results[m][rf][sf] is not None):
        hlp.register_error("Cannot plot latency vs load for %s because RapidChiplet results are missing." % name)
    if not all("booksim_simulation" in results[m][rf][sf]["rapidchiplet"] for m in results for rf in results[m] for sf in results[m][rf] if results[m][rf][sf] is not None):
        hlp.register_error("Cannot plot latency vs load for %s because BookSim simulation results are missing." % name)
    # Flat version of results
    results_flat = [results[m][rf][sf] for m in results for rf in results[m] for sf in results[m][rf] if results[m][rf][sf] is not None]
    if len(results_flat) == 0:
        print("Warning: No valid results found for plotting latency vs load for %s." % name)
        return
    # Create the plot
    fig, ax = plt.subplots(figsize=(10, 4))
    fig.subplots_adjust(left = 0.075, right = 0.65, top = 0.925, bottom = 0.125)
    upper_bound_factor = 1.25
    # Determine global min and max latency to set y-axis limits
    min_lat = min([row["detailed"][load]["packet_latency"]["avg"] for res in results_flat if res != None for row in res["rapidchiplet"]["booksim_simulation"] for load in row["detailed"].keys() if hlp.is_float(load) and row["detailed"][load]["status"] == "Success"])
    max_lat = max([row["detailed"][load]["packet_latency"]["avg"] for res in results_flat if res != None for row in res["rapidchiplet"]["booksim_simulation"] for load in row["detailed"].keys() if hlp.is_float(load) and row["detailed"][load]["status"] == "Success"])
    max_zero_lat = max([float(np.mean([row["summary"]["zero_load_latency"] for row in res["rapidchiplet"]["booksim_simulation"]])) for res in results_flat if res != None])
    # Set upper bound for y-axis
    bound = max_zero_lat * upper_bound_factor
    # Plot each method; routing function; selection function combination
    cnt = 0
    for (i, m) in enumerate(results.keys()):
        if results[m] is None:
            continue
        for (j, rf) in enumerate(results[m].keys()):
            if results[m][rf] is None:
                continue
            for (k, sf) in enumerate(results[m][rf].keys()):
                if results[m][rf][sf] is None:
                    continue
                res = results[m][rf][sf]
                all_loads = list(sorted(set(float(load) for run in res["rapidchiplet"]["booksim_simulation"] for load in run["detailed"].keys() if hlp.is_float(load) and run["detailed"][load]["status"] == "Success")))
                lats_per_load = {load : [run["detailed"][str(load)]["packet_latency"]["avg"] for run in res["rapidchiplet"]["booksim_simulation"] if str(load) in run["detailed"] and "packet_latency" in run["detailed"][str(load)]] for load in all_loads} 
                avg_lats = [float(np.mean(lats_per_load[load])) for load in all_loads]
                min_lats = [float(np.min(lats_per_load[load])) for load in all_loads]
                max_lats = [float(np.max(lats_per_load[load])) for load in all_loads]

                # Add vertical line for saturation throughput
                all_loads.append(all_loads[-1])
                avg_lats.append(bound * 1.2)
                min_lats.append(bound * 1.2)
                max_lats.append(bound * 1.2)


                # Loads in bytes/node/cycle instead of flits/node/cycle
                all_loads_bytes = []
                for load in all_loads:
                    flits_per_node = load
                    flit_size = cfg.link_bandwidth_bit_per_sec / cfg.network_frequency_hz
                    bytes_per_node = flits_per_node * (flit_size / 8)
                    all_loads_bytes.append(bytes_per_node)

                # Plot the data
                col = cfg.colors[cnt % len(cfg.colors)]
                mar = cfg.markers[cnt % len(cfg.markers)]
                lab = "%s (%s, %s)" % (label_map[m], label_map[rf], label_map[sf])
                ax.plot(all_loads_bytes, avg_lats, label=lab, color = col, linewidth = 2, marker=mar, markersize=5)
                ax.fill_between(all_loads_bytes, min_lats, max_lats, color = col, alpha = 0.3)

                # Update counter (for colors and markers)
                cnt += 1
    # X-Axis
    ax.set_xlim(left = -0.001)
    ax.set_xlabel("Injection Rate [Bytes/node/cycle]")
    # Y-Axis
    if not math.isnan(bound):
        ax.set_ylim(min_lat * 0.9, bound)
    ax.set_ylabel("Average Packet Latency [cycles]")
    # General
    ax.set_title("Latency vs Load of %s" % name)
    ax.legend(bbox_to_anchor=(1.01, 1), loc='upper left', fontsize=11)
    ax.grid(True)
    # Save the figure
    plt.savefig("plots/" + name + "_latency_vs_load." + cfg.plot_format, dpi=cfg.plot_dpi)
    plt.close(fig)

# Deprecated: Might not work with the new result format
def plot_rapidchiplet_vs_booksim(results: Dict, name: str) -> None:
    # Compute some intermediates
    flit_size = cfg.link_bandwidth_bit_per_sec / cfg.network_frequency_hz       # In bit
    # Prepare data for plotting
    labels = []
    bs_lats_mean = []
    bs_lats_std = []
    rc_lats = []
    bs_tps_mean = []
    bs_tps_std = []
    rc_tps = []
    for integration_level in results:
        for wafer_diameter in results[integration_level]:
            for wafer_utilization in results[integration_level][wafer_diameter]:
                for method in results[integration_level][wafer_diameter][wafer_utilization]:
                    res = results[integration_level][wafer_diameter][wafer_utilization][method]
                    if res is None:
                        continue
                    if "rapidchiplet" not in res or "booksim_simulation" not in res["rapidchiplet"]:
                        hlp.register_error("Cannot compare RapidChiplet and BookSim for %s_%dmm_%s_%s because simulation results are missing." % (integration_level, wafer_diameter, wafer_utilization, method))
                    labels.append("%s_%dmm_%s_%s" % (integration_level, wafer_diameter, wafer_utilization, method))
                    bs_lats = [res["rapidchiplet"]["booksim_simulation"][i]["summary"]["zero_load_latency"] for i in range(len(res["rapidchiplet"]["booksim_simulation"]))]
                    bs_lats_mean.append(float(np.mean(bs_lats)))
                    bs_lats_std.append(float(np.std(bs_lats)))
                    rc_lats.append(res["rapidchiplet"]["latency"]["avg"])
                    bs_tps = [res["rapidchiplet"]["booksim_simulation"][i]["summary"]["saturation_throughput"] for i in range(len(res["rapidchiplet"]["booksim_simulation"]))]
                    bs_tps_mean.append(float(np.mean(bs_tps)))
                    bs_tps_std.append(float(np.std(bs_tps)))
                    rc_tps.append(res["rapidchiplet"]["throughput"]["aggregate_throughput"] / (res["topology_analysis"]["n_compute_reticles"] * cfg.number_of_gpcs * flit_size)) # Convert throughput from total bits/cycle to flits/node/cycle (i.e. injection rate)
    # Create grouped bars plot. Subplot 1: Latency comparison, Subplot 2: Throughput comparison
    x = np.arange(len(labels))  # the label locations
    width = 0.35  # the width of the bars
    fig, ax = plt.subplots(1, 2, figsize=(24, 6))
    # Subplot 1: Latency comparison
    ax[0].errorbar(x - width/2, bs_lats_mean, yerr=bs_lats_std, fmt='.', capsize=4, color="#000000", zorder=4)
    ax[0].bar(x - width/2, bs_lats_mean, width, label='BookSim', color=cfg.colors[0], zorder=3)
    ax[0].bar(x + width/2, rc_lats, width, label='RapidChiplet', color=cfg.colors[1], zorder=3)
    ax[0].set_ylabel('Average Packet Latency [cycles]')
    ax[0].set_title('Latency Comparison')
    ax[0].set_xticks(x)
    ax[0].set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
    ax[0].legend()
    ax[0].grid(axis='y', zorder=0)
    # Subplot 2: Throughput comparison
    ax[1].errorbar(x - width/2, bs_tps_mean, yerr=bs_tps_std, fmt='.', capsize=4, color="#000000", zorder=4)
    ax[1].bar(x - width/2, bs_tps_mean, width, label='BookSim', color=cfg.colors[0], zorder=3)
    ax[1].bar(x + width/2, rc_tps, width, label='RapidChiplet', color=cfg.colors[1], zorder=3)
    ax[1].set_ylabel('Saturation Throughput [flits/node/cycle]')
    ax[1].set_title('Throughput Comparison')
    ax[1].set_xticks(x)
    ax[1].set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
    ax[1].legend()
    ax[1].grid(axis='y', zorder=0)
    plt.tight_layout()
    # Save the figure
    plt.savefig("plots/" + name + "_rapidchiplet_vs_booksim." + cfg.plot_format, dpi=cfg.plot_dpi)
    plt.close(fig)


# A grain of salt: We can only compute the overall link power of the system as BookSim does not report the per-link utilization
# Therefore, the power breakdown of the compute and interconnect reticles is only of limited usability.
# A second grain of salt: The "highest common throughput" mode plot will take 0.001 as throughput if one methods achieves less than 0.01 and one achieves more than 0.01
# Since the one achieving more will only evaluate 0.001, 0.01 and higher loads. If we include this into the paper, we need to modify the experiment runner to ensure that all methods evaluate a common loads.
def plot_area_and_power_brakdown(results: Dict, name: str, technology : str, mode : str) -> None:
    """
    Plot the area and power breakdown for the overall system as well as for the compute and interconnect reticles (if applicable).
    Arguments:
    - results: Dictionary with results 
    - name: Name of the design
    - technology: Technology node to plot (can be "7nm" or "45nm")
    - mode: Mode to plot (can be "saturation throughput", "highest common throughput")
    """

    # Determine the integration level and whether we use one or two reticle types
    has_intercon_reticle = False
    if "logic_and_interconnect" in name:
        has_intercon_reticle = True
    elif "logic_and_logic" in name:
        has_intercon_reticle = False
    else:
        hlp.register_error("Cannot determine integration level from name %s. Skipping area and power breakdown plot." % name)
    reticle_area = cfg.parameters["reticle_size"][0] * cfg.parameters["reticle_size"][1] # in mm^2
    # If the mode is "highest common throughput", we need to identify the highest load that all methods can sustain
    if mode == "highest common throughput":
        # For booksim, we perform multiple runs. Here, we identify the median run based on the saturation throughput
        median_booksim_runs = {}
        for method in results:
            saturation_throughputs = [results[method]["rapidchiplet"]["booksim_simulation"][rep]["summary"]["saturation_throughput"] for rep in range(len(results[method]["rapidchiplet"]["booksim_simulation"]))]
            sorted_data = sorted((value, index) for index, value in enumerate(saturation_throughputs))
            median_rep = sorted_data[len(sorted_data) // 2][1]
            median_booksim_runs[method] = results[method]["rapidchiplet"]["booksim_simulation"][median_rep]
        # Identify the highest load that all methods can sustain
        all_loads_by_method = [[float(load) for load in median_booksim_runs[method]["detailed"].keys() if hlp.is_float(load) and median_booksim_runs[method]["detailed"][load]["status"] == "Success"] for method in results if results[method] is not None]
        all_loads = list(set([load for sublist in all_loads_by_method for load in sublist]))
        highest_common_load = max([load for load in all_loads if all(load in loads for loads in all_loads_by_method)])
    nppm = 3 if has_intercon_reticle else 2 # number of plots per metric
    fig, ax = plt.subplots(1, 2 * nppm, figsize=(12 * nppm, 6))
    fig.subplots_adjust(left = 0.05, right = 0.95, top = 0.85, bottom = 0.15, wspace = 0.4)
    txt = mode + ((" (" + str(highest_common_load) + ")") if mode == "highest common throughput" else "")
    plt.suptitle("Area and Power Breakdown of %s on %s (%s)" % (name, technology, txt), fontsize=16)
    for (i, method) in enumerate(results.keys()):
        if results[method] is None:
            continue
        res = results[method]
        # Check if area and power summary is present, if not add it
        if ("area_summary_" + technology) not in res:
            hlp.register_error("Area summary for technology %s not found in results for design %s with method %s." % (technology, name, method))
        if ("power_summary_" + technology) not in res:
            hlp.register_error("Power summary for technology %s not found in results for design %s with method %s." % (technology, name, method))
        factor = {"area" : 1e-6, "power" : 1e-3} # um^2 to mm^2, mW to W
        # Plot area and power breakdowns
        for (j, metric) in enumerate(["area", "power"]):
            letter = metric[0].upper()
            # Add one bar to the system area and power plot for this method
            pid = j * nppm
            metric_by_component = {key : val * factor[metric] for (key,val) in res["%s_summary_%s" % (metric, technology)].items() if key != (letter + "total")}
            # If the mode uses the highest common throughput, we overwrite the link power with the value from the power summary
            link_power_of_whole_system = 0.0
            if mode == "highest common throughput" and metric == "power":
                zero_latency_avg = float(np.mean([res["rapidchiplet"]["booksim_simulation"][rep]["summary"]["zero_load_latency"] for rep in range(len(res["rapidchiplet"]["booksim_simulation"]))]))    
                hops_avg = float(np.mean([res["rapidchiplet"]["booksim_simulation"][rep]["detailed"][str(highest_common_load)]["hops"]["avg"] for rep in range(len(res["rapidchiplet"]["booksim_simulation"]))]))
                metric_by_component["Plink"] = pas.compute_link_power(highest_common_load, zero_latency_avg, hops_avg, res["topology_analysis"]["n_compute_reticles"], technology) * factor[metric]
                link_power_of_whole_system = metric_by_component["Plink"]
            elif mode == "saturation throughput" and metric == "power":
                link_power_of_whole_system = res["power_summary_" + technology]["Plink"] * factor[metric]
            elif metric == "power":
                hlp.register_error("Invalid mode %s. Skipping area and power breakdown plot." % mode)
            bottom = 0
            for (k, (key, val)) in enumerate(metric_by_component.items()):
                ax[pid].bar(i, val, bottom = bottom, label = key if i == 0 else "", color = cfg.colors[k % len(cfg.colors)], zorder=3)
                bottom += val
            # Title and axis
            if i == len(results) - 1:
                ax[pid].set_title("Overall system %s" % metric.capitalize())
                ax[pid].set_xlabel("Reticle Placement Method")
                ax[pid].set_ylabel("%s [%s]" % (metric.capitalize(), "mm$^2$" if metric == "area" else "W"))
                ax[pid].set_xticks(range(len(results)))
                ax[pid].set_xticklabels(results.keys(), rotation=45, ha='right', fontsize=8)
                ax[pid].grid(axis='y', zorder=0)
                ax[pid].legend(fontsize=8)
            # Add bar for the compute and interconnect reticles if applicable
            for (o, typ) in enumerate(["compute", "interconnect"]):
                # Skip interconnect reticle if not applicable
                if typ == "interconnect" and not has_intercon_reticle:
                    continue
                orion_results = [res["orion3"][key] for key in res["orion3"] if key.startswith(typ)]
                if len(orion_results) == 0:
                    hlp.register_error("No Orion results found for %s reticle in design %s." % (typ, name))
                elif len(orion_results) > 1:
                    hlp.register_error("Multiple Orion results found for %s reticle in design %s. Using the first one." % (typ, name))
                else:
                    pid = j * nppm + 1 + o
                    orion_result = orion_results[0]
                    tech_factor = ((cfg.area_scaling_factor_45nm_to_7nm if metric == "area" else cfg.power_scaling_factor_45nm_to_7nm) if technology == "7nm" else 1.0)
                    metric_by_component = {key : val * factor[metric] * tech_factor for (key,val) in orion_result.items() if (key[0] == letter and key != (letter + "total"))}
                    # Add an estimate of the link power. We assume that compute and interconnect reticles have the same link power, which is not necessarily true. But we do not have more detailed information form our simulation.
                    if metric == "power":
                        metric_by_component["Plink"] = link_power_of_whole_system / res["topology_analysis"]["n_reticles"]
                    bottom = 0
                    for (k, (key, val)) in enumerate(metric_by_component.items()):
                        ax[pid].bar(i, val, bottom = bottom, label = key if i == 0 else "", color = cfg.colors[k % len(cfg.colors)], zorder=3)
                        bottom += val
                    if i == len(results) - 1:
                        ax[pid].set_title("%s of %s reticle" % (metric.capitalize(), typ))
                        ax[pid].set_xlabel("Reticle Placement Method")
                        ax[pid].set_ylabel("%s [%s]" % (metric.capitalize(), "mm$^2$" if metric == "area" else "W"))
                        ax[pid].set_xticks(range(len(results)))
                        ax[pid].set_xticklabels(results.keys(), rotation=45, ha='right', fontsize=8)
                        ax[pid].grid(axis='y', zorder=0)
                        ax[pid].legend(fontsize=8)
                        # Add second axis for percentage of total reticle for area metric
                        if metric == "area":
                            ax2 = ax[pid].twinx()
                            ylims = ax[pid].get_ylim()
                            ax2.set_ylim([v / reticle_area * 100 for v in ylims])
                            ax2.set_ylabel("Fraction of Reticle area [%]")
    # Save the figure
    plt.savefig("plots/" + name + "_area_and_power_breakdown_" + technology + "." + cfg.plot_format, dpi=cfg.plot_dpi)
    plt.close(fig)

# Deprecated: Might not work with the new result format
# The correlation analysis uses the Orion3.0 results for area and power which are based on 45nm technology. Since 7nm numbers are just scaled by a factor, the correlation analysis would look the same for 7nm.
def plot_correlation_analysis(results : Dict, name : str) -> None:
    n_metrics = 9
    fig, ax = plt.subplots(n_metrics, n_metrics, figsize=(4 * n_metrics, 4 * n_metrics))
    # Iterate through architectures
    color_idx = 0
    for integration_level in results:
        for wafer_diameter in results[integration_level]:
            for wafer_utilization in results[integration_level][wafer_diameter]:
                all_results = [results[integration_level][wafer_diameter][wafer_utilization][m] for m in results[integration_level][wafer_diameter][wafer_utilization] if results[integration_level][wafer_diameter][wafer_utilization][m] is not None]
                methods = [m for m in results[integration_level][wafer_diameter][wafer_utilization].keys() if results[integration_level][wafer_diameter][wafer_utilization][m] is not None]
                # Prepare the metrics
                metrics = {}
                metrics["diameter"] = [res["topology_analysis"]["diameter"] for res in all_results]
                metrics["bisection_bandwidth"] = [res["topology_analysis"]["bisection_bandwidth_mean"] for res in all_results]
                metrics["average_path_length"] = [res["topology_analysis"]["path_length_mean"] for res in all_results]
                metrics["zero_load_latency"] = [float(np.mean([res["rapidchiplet"]["booksim_simulation"][i]["summary"]["zero_load_latency"] for i in range(len(res["rapidchiplet"]["booksim_simulation"]))])) for res in all_results]
                metrics["saturation_throughput"] = [float(np.mean([res["rapidchiplet"]["booksim_simulation"][i]["summary"]["saturation_throughput"] for i in range(len(res["rapidchiplet"]["booksim_simulation"]))])) for res in all_results]
                metrics["compute_reticle_area"] = []
                metrics["interconnect_reticle_area"] = []
                metrics["compute_reticle_power"] = []
                metrics["interconnect_reticle_power"] = []
                for res in all_results:
                    for typ in ["compute", "interconnect"]:
                        for metric in ["area", "power"]:
                            keys = [key for key in res["orion3"] if key.startswith(typ)]
                            if len(keys) == 0:
                                # This happens for the logic_and_logic integration level, which does not have an interconnect reticle
                                if typ == "interconnect":
                                    metrics["interconnect_reticle_%s" % metric].append(0.0)
                                else:
                                    hlp.register_error("No Orion results found for %s reticle." % typ)
                            elif len(keys) > 1:
                                hlp.register_error("Multiple Orion results found for %s reticle." % typ)
                            else:
                                orion_result = res["orion3"][keys[0]]
                                metrics["%s_reticle_%s" % (typ, metric)].append(orion_result[metric[0].upper() + "total"] * (1e-6 if metric == "area" else 1e-3))   # Convert um^2 to mm^2 and mW to W
                # Iterate through the subplots
                for i, metric_x in enumerate(metrics.keys()):
                    for j, metric_y in enumerate(metrics.keys()):
                        # Diagonal: Plot a legend with circle colors for architectures and black markers for methods
                        if i == j:
                            if color_idx == 0:
                                ax[i][j].axis('off')
                                # Add architecture legend
                                for k, (il, wd, wu) in enumerate([(integration_level, wafer_diameter, wafer_utilization) for integration_level in results for wafer_diameter in results[integration_level] for wafer_utilization in results[integration_level][wafer_diameter]]):
                                    col = cfg.colors[k % len(cfg.colors)]
                                    ax[i][j].plot([], [], '*', color=col, label="%s, %dmm, %s" % (il, wd, wu))
                                # Add method legend
                                for k, method in enumerate(methods):
                                    mar = cfg.markers[k % len(cfg.markers)]
                                    ax[i][j].plot([], [], marker=mar, color='black', linestyle='none', label=method)
                                ax[i][j].legend(fontsize=8, bbox_to_anchor=(0.5, 0.5), loc='center')
                        # Non-Diagonal: Plot correlation
                        else:
                            col = cfg.colors[color_idx % len(cfg.colors)]
                            # Sort x and y metric according to x metric to get a nicer line
                            xvals, yvals = zip(*sorted(zip(metrics[metric_x], metrics[metric_y])))
                            # Skip architectures where one of the metrics is always zero (area and power of interconnect reticle for logic_and_logic integration level)
                            if max(xvals) == 0 or max(yvals) == 0:
                                continue    
                            ax[i][j].plot(xvals, yvals, 'none', color=col, linestyle=':', zorder=3)
                            for k in range(len(methods)):
                                mar = cfg.markers[k % len(cfg.markers)]
                                ax[i][j].plot(xvals[k], yvals[k], marker=mar, color=col, zorder=4)
                            ax[i][j].set_xlabel(metric_x.replace("_", " ").capitalize())
                            ax[i][j].set_ylabel(metric_y.replace("_", " ").capitalize())
                            ax[i][j].grid(True, zorder=0)
                color_idx += 1
    plt.tight_layout()
    # Save the figure
    plt.savefig("plots/" + name + "_correlation_analysis." + cfg.plot_format, dpi=cfg.plot_dpi)
    plt.close(fig)

# Deprecated: Might not work with the new result format
def plot_sample_period_analysis(results : Dict, name : str) -> None:
    fig, ax = plt.subplots(1, 4, figsize=(30, 6))
    fig.subplots_adjust(left = 0.05, right = 1.0, top = 0.85, bottom = 0.15, wspace = 0.3)
    # Iterate through architectures
    color_idx = 0
    for integration_level in results:
        for wafer_diameter in results[integration_level]:
            for wafer_utilization in results[integration_level][wafer_diameter]:
                all_results = [results[integration_level][wafer_diameter][wafer_utilization][m] for m in results[integration_level][wafer_diameter][wafer_utilization] if results[integration_level][wafer_diameter][wafer_utilization][m] is not None and "sample_period_analysis" in results[integration_level][wafer_diameter][wafer_utilization][m]]
                methods = [m for m in results[integration_level][wafer_diameter][wafer_utilization].keys() if results[integration_level][wafer_diameter][wafer_utilization][m] is not None and "sample_period_analysis" in results[integration_level][wafer_diameter][wafer_utilization][m]]
                # Prepare the metrics
                sample_periods = sorted(list(set([int(sp) for res in all_results for sp in res["sample_period_analysis"].keys()])))
                latencies = [[([row["summary"]["zero_load_latency"] for row in res["sample_period_analysis"][str(sp)]["rapidchiplet"]["booksim_simulation"]] if str(sp) in res["sample_period_analysis"] else float("nan")) for sp in sample_periods] for res in all_results]
                throughputs = [[([row["summary"]["saturation_throughput"] for row in res["sample_period_analysis"][str(sp)]["rapidchiplet"]["booksim_simulation"]] if str(sp) in res["sample_period_analysis"] else float("nan")) for sp in sample_periods] for res in all_results]
                latencies_mean = [[float(np.mean(latencies[i][j])) if type(latencies[i][j]) == list and len(latencies[i][j]) > 0 else float("nan") for j in range(len(sample_periods))] for i in range(len(methods))]
                throughputs_mean = [[float(np.mean(throughputs[i][j])) if type(throughputs[i][j]) == list and len(throughputs[i][j]) > 0 else float("nan") for j in range(len(sample_periods))] for i in range(len(methods))]
                latencies_std = [[float(np.std(latencies[i][j])) if type(latencies[i][j]) == list and len(latencies[i][j]) > 0 else float("nan") for j in range(len(sample_periods))] for i in range(len(methods))]
                throughputs_std = [[float(np.std(throughputs[i][j])) if type(throughputs[i][j]) == list and len(throughputs[i][j]) > 0 else float("nan") for j in range(len(sample_periods))] for i in range(len(methods))]
                latency_error = [[100 * latencies_mean[i][j] / latencies_mean[i][-1] - 100 if not np.isnan(latencies_mean[i][j]) else float("nan") for j in range(len(sample_periods))] for i in range(len(methods))]
                throughput_error = [[100 * throughputs_mean[i][j] / throughputs_mean[i][-1] - 100 if not np.isnan(throughputs_mean[i][j]) else float("nan") for j in range(len(sample_periods))] for i in range(len(methods))]
                # Iterate through methods
                for (i, method) in enumerate(methods):
                    col = cfg.colors[color_idx % len(cfg.colors)]
                    mar = cfg.markers[i % len(cfg.markers)]
                    lab = "%s, %s, %dmm, %s" % (integration_level, wafer_utilization, wafer_diameter, method)
                    # Latency plot
                    ax[0].errorbar(sample_periods, latencies_mean[i], yerr=latencies_std[i], fmt='.', capsize=4, color=col, zorder=4, label=lab, linestyle = "-", linewidth = 0.5, marker=mar, markersize=3)
                    # Throughput plot
                    ax[1].errorbar(sample_periods, throughputs_mean[i], yerr=throughputs_std[i], fmt='.', capsize=4, color=col, zorder=4, label=lab, linestyle = "-", linewidth = 0.5, marker=mar, markersize=3)
                    # Latency error plot
                    ax[2].plot(sample_periods, latency_error[i], color=col, zorder=4, label=lab, linestyle = "-", linewidth = 0.5, marker=mar, markersize=3)
                    # Throughput error plot
                    ax[3].plot(sample_periods, throughput_error[i], color=col, zorder=4, label=lab, linestyle = "-", linewidth = 0.5, marker=mar, markersize=3)
                color_idx += 1
    # X-Axis
    for i in range(4):
        ax[i].set_xlabel("Sample Period [cycles]")
        ax[i].set_xscale('log', base=2)
        ax[i].set_xticks(sample_periods)
        ax[i].set_xticklabels([str(sp) for sp in sample_periods], fontsize=8)
        ax[i].grid(True, which='both', zorder=0)
    # Y-Axis
    ax[0].set_ylabel("Average Packet Latency [cycles]")
    ax[1].set_ylabel("Saturation Throughput [flits/node/cycle]")
    ax[2].set_ylabel("Latency Error [% of max]")
    ax[3].set_ylabel("Throughput Error [% of max]")
    ax[1].set_ylim(0, 0.2)
    ax[3].set_ylim(-10, 200)
    # General
    ax[0].set_title("Latency vs Sample Period of %s" % name)
    ax[1].set_title("Throughput vs Sample Period of %s" % name)
    ax[2].set_title("Latency Error vs Sample Period of %s" % name)
    ax[3].set_title("Throughput Error vs Sample Period of %s" % name)
    ax[3].legend(fontsize=8, bbox_to_anchor=(1.4, 0.5), loc='center')
    plt.tight_layout()
    # Save the figure
    plt.savefig("plots/" + name + "_sample_period_analysis." + cfg.plot_format, dpi=cfg.plot_dpi)

# Deprecated: Might not work with the new result format
def plot_vc_buffer_analysis(results : Dict, name : str) -> None:
    fig, ax = plt.subplots(1, 4, figsize=(30, 6))
    fig.subplots_adjust(left = 0.05, right = 1.0, top = 0.85, bottom = 0.15, wspace = 0.3)
    # Iterate through architectures
    color_idx = 0
    for integration_level in results:
        for wafer_diameter in results[integration_level]:
            for wafer_utilization in results[integration_level][wafer_diameter]:
                all_results = [results[integration_level][wafer_diameter][wafer_utilization][m] for m in results[integration_level][wafer_diameter][wafer_utilization] if results[integration_level][wafer_diameter][wafer_utilization][m] is not None]
                methods = [m for m in results[integration_level][wafer_diameter][wafer_utilization].keys() if results[integration_level][wafer_diameter][wafer_utilization][m] is not None]
                # Prepare the metrics
                vc_buffers = sorted(list(set([int(vcb) for res in all_results if "vc_buffer_analysis" in res for vcb in res["vc_buffer_analysis"].keys()])))
                latencies = [[([row["summary"]["zero_load_latency"] for row in res["vc_buffer_analysis"][str(vcb)]["rapidchiplet"]["booksim_simulation"]] if str(vcb) in res["vc_buffer_analysis"] else float("nan")) for vcb in vc_buffers] for res in all_results if "vc_buffer_analysis" in res]
                throughputs = [[([row["summary"]["saturation_throughput"] for row in res["vc_buffer_analysis"][str(vcb)]["rapidchiplet"]["booksim_simulation"]] if str(vcb) in res["vc_buffer_analysis"] else float("nan")) for vcb in vc_buffers] for res in all_results if "vc_buffer_analysis" in res]
                latencies_mean = [[float(np.mean(latencies[i][j])) if type(latencies[i][j]) == list and len(latencies[i][j]) > 0 else float("nan") for j in range(len(vc_buffers))] for i in range(len(methods))]
                throughputs_mean = [[float(np.mean(throughputs[i][j])) if type(throughputs[i][j]) == list and len(throughputs[i][j]) > 0 else float("nan") for j in range(len(vc_buffers))] for i in range(len(methods))]
                latencies_std = [[float(np.std(latencies[i][j])) if type(latencies[i][j]) == list and len(latencies[i][j]) > 0 else float("nan") for j in range(len(vc_buffers))] for i in range(len(methods))]
                throughputs_std = [[float(np.std(throughputs[i][j])) if type(throughputs[i][j]) == list and len(throughputs[i][j]) > 0 else float("nan") for j in range(len(vc_buffers))] for i in range(len(methods))]
                latency_error = [[100 * latencies_mean[i][j] / latencies_mean[i][-1] - 100 if not np.isnan(latencies_mean[i][j]) else float("nan") for j in range(len(vc_buffers))] for i in range(len(methods))]
                throughput_error = [[100 * throughputs_mean[i][j] / throughputs_mean[i][-1] - 100 if not np.isnan(throughputs_mean[i][j]) else float("nan") for j in range(len(vc_buffers))] for i in range(len(methods))]
                # Iterate through methods
                for (i, method) in enumerate(methods):
                    col = cfg.colors[color_idx % len(cfg.colors)]
                    mar = cfg.markers[i % len(cfg.markers)]
                    lab = "%s, %s, %dmm, %s" % (integration_level, wafer_utilization, wafer_diameter, method)
                    # Latency plot
                    ax[0].errorbar(vc_buffers, latencies_mean[i], yerr=latencies_std[i], fmt='.', capsize=4, color=col, zorder=4, label=lab, linestyle = "-", linewidth = 0.5, marker=mar, markersize=3)
                    # Throughput plot
                    ax[1].errorbar(vc_buffers, throughputs_mean[i], yerr=throughputs_std[i], fmt='.', capsize=4, color=col, zorder=4, label=lab, linestyle = "-", linewidth = 0.5, marker=mar, markersize=3)
                    # Latency error plot
                    ax[2].plot(vc_buffers, latency_error[i], color=col, zorder=4, label=lab, linestyle = "-", linewidth = 0.5, marker=mar, markersize=3)
                    # Throughput error plot
                    ax[3].plot(vc_buffers, throughput_error[i], color=col, zorder=4, label=lab, linestyle = "-", linewidth = 0.5, marker=mar, markersize=3)
                color_idx += 1
    # X-Axis
    for i in range(4):
        ax[i].set_xlabel("VC Buffer Size [flits]")
        ax[i].set_xscale('log', base=2)
        ax[i].set_xticks(vc_buffers)
        ax[i].set_xticklabels([str(vcb) for vcb in vc_buffers], fontsize=8)
        ax[i].grid(True, which='both', zorder=0)
    # Y-Axis
    ax[0].set_ylabel("Average Packet Latency [cycles]")
    ax[1].set_ylabel("Saturation Throughput [flits/node/cycle]")
    ax[2].set_ylabel("Latency Overhead [%]")
    ax[3].set_ylabel("Throughput Insufficiency [%]")
    ax[1].set_ylim(0, 0.05)
    ax[3].set_ylim(-100, 10)
    # General
    ax[0].set_title("Latency vs VC Buffer Size of %s" % name)
    ax[1].set_title("Throughput vs VC Buffer Size of %s" % name)
    ax[2].set_title("Latency Overhead vs VC Buffer Size of %s" % name)
    ax[3].set_title("Throughput Insufficiency vs VC Buffer Size of %s" % name)
    ax[3].legend(fontsize=8, bbox_to_anchor=(1.4, 0.5), loc='center')
    plt.tight_layout()
    # Save the figure
    plt.savefig("plots/" + name + "_vc_buffer_analysis." + cfg.plot_format, dpi=cfg.plot_dpi)


# Create a heatmap with one column per (integration level, wafer diameter, wafer utilization) combination and one row per method
def plot_heatmap_vs_baseline(results, metric, name):
    def get_metric_value(res):
        if metric == "latency":
            return float(np.mean([res["rapidchiplet"]["booksim_simulation"][i]["summary"]["zero_load_latency"] for i in range(len(res["rapidchiplet"]["booksim_simulation"]))]))
        elif metric == "throughput":
            flits_per_node =float(np.mean([res["rapidchiplet"]["booksim_simulation"][i]["summary"]["saturation_throughput"] for i in range(len(res["rapidchiplet"]["booksim_simulation"]))]))
            flit_size = cfg.link_bandwidth_bit_per_sec / cfg.network_frequency_hz
            bytes_per_node = flits_per_node * (flit_size / 8)
            bytes_per_gpu = bytes_per_node * cfg.number_of_gpcs
            return bytes_per_gpu
        elif metric == "energy":
            if "power_summary_7nm" not in res:
                hlp.register_error("Power summary for 7nm not found in results. Skipping heatmap vs baseline plot.")
                return None
            return res["power_summary_7nm"]["energy_per_byte_in_pJ"]
        elif metric == "trace-latency":
            return float(np.mean([res["rapidchiplet"]["booksim_simulation"][i]["detailed"]["trace"]["network_latency"]["avg"] for i in range(len(res["rapidchiplet"]["booksim_simulation"]))]))
        else:
            hlp.register_error("Invalid metric %s. Skipping heatmap vs baseline plot." % metric)
            return None
    architectures = sorted(list(set([(wd, wu, rf, sf) for wd in results for wu in results[wd] for m in results[wd][wu] for rf in results[wd][wu][m] for sf in results[wd][wu][m][rf]])))
    methods = sorted(list(set([m for wd in results for wu in results[wd] for m in results[wd][wu] if results[wd][wu][m] is not None])))
    data = np.zeros((len(methods), len(architectures)))
    data_raw_values = np.zeros((len(methods), len(architectures)))
    for (j, arch) in enumerate(architectures):
        wd, wu, rf, sf = arch
        baseline = results[wd][wu]["baseline"][rf][sf] if "baseline" in results[wd][wu].keys() else None
        # Skip if no baseline is found
        if baseline is None:
            continue
            balselin_value = float("nan")
        else:
            baseline_value = get_metric_value(baseline)
        # Iterate through methods
        for (i, method) in enumerate(methods):
            if method in results[wd][wu].keys():
                res = results[wd][wu][method][rf][sf]
                if res is not None:
                    value = get_metric_value(res)
                    if value is None or baseline_value is None or baseline_value == 0:
                        data[i][j] = float("nan")
                        data_raw_values[i][j] = float("nan")
                    else:
                        data[i][j] = (value / baseline_value) * 100
                        data_raw_values[i][j] = value
                else:
                    data[i][j] = float("nan")
                    data_raw_values[i][j] = float("nan")
            else:
                data[i][j] = float("nan")
                data_raw_values[i][j] = float("nan")
    unit = {"latency" : " cycles", "throughput" : " bytes/GPU/cycle", "energy" : " pJ/byte", "trace-latency" : "cycles"}[metric]
    unit_short = {"latency" : "c", "throughput" : "B/G/c", "energy" : "pJ/B", "trace-latency" : "c"}[metric]
    fig, ax = plt.subplots(figsize=(len(architectures), 2+len(methods)))
    diff = max(abs(100-np.nanmin(data)), abs(np.nanmax(data)-100))
    cmap = "RdYlGn" if metric in ["throughput"] else "RdYlGn_r"
    norm = mcolors.TwoSlopeNorm(vmin=50, vcenter=100, vmax=200)
    cax = ax.matshow(data, cmap=cmap, norm = norm, aspect = 0.4)
    fig.colorbar(cax, label='%s vs Baseline [%%]' % metric.capitalize(), fraction=0.02, pad=0.04)
    # Add text annotations
    for (i, method) in enumerate(methods):
        for (j, arch) in enumerate(architectures):
            if not np.isnan(data[i][j]):
                if method == "baseline":
                    if "trace" in metric:
                        ax.text(j, i, "%.4g %s" % (data_raw_values[i][j],unit_short), va='center', ha='center', color='black', fontsize=8, rotation=0, fontweight='bold')
                    else:
                        ax.text(j, i, "%.3g %s" % (data_raw_values[i][j],unit_short), va='center', ha='center', color='black', fontsize=8, rotation=0, fontweight='bold')
                else:
                    ax.text(j, i, "%.0f%%" % data[i][j], va='center', ha='center', color='black', fontsize=10, rotation=0)
    # Axis labels and title
    ax.xaxis.set_ticks_position('bottom')
    ax.set_xticks(range(len(architectures)))
    ax.set_xticklabels(["%dmm, %s, %s, %s" % (arch[0], arch[1], arch[2], arch[3]) for arch in architectures], rotation=90, ha='right', fontsize=8)
    ax.set_yticks(range(len(methods)))
    ax.set_yticklabels([label_map[method] for method in methods], fontsize=8)
    ax.set_xlabel("Architecture")
    ax.set_ylabel("Method")
    ax.set_title("%s in %s for %s traffic"  % (metric.capitalize(), unit, name.split("_")[-1]), fontsize=10)
    plt.tight_layout()
    # Save the figure
    plt.savefig("plots/%s_heatmap_vs_baseline_%s.%s" % (name, metric, cfg.plot_format), dpi=cfg.plot_dpi)
    plt.close(fig)


def create_overview_table(results : Dict, name : str) -> None:
    """
    Generates a LaTeX table summarizing architecture metrics, using \multirow 
    to group adjacent rows that share the same Integration Level, Wafer Diameter,
    and Wafer Utilization. The internal horizontal rules (\cline) only span the
    non-multirow columns, adapting their starting column based on the grouping hierarchy.
    """
    params_fixed = {
        "routing_function" : "simple_cycle_breaking_set",
        "selection_function" : "random",
        "traffic" : "uniform"
    }
    metric_to_label = {
        "n_compute_reticles" : "Number of Compute\\\\Reticles (26$\\times$33mm)",
        "n_interconnect_reticles" : "Number of Interconnect\\\\Reticles ($\\approx$26$\\times$33mm)", 
        "compute_radix" : "Radix of\\\\Compute Reticles",
        "interconnect_radix" : "Radix of\\\\Interconnect Reticles",
        "diameter" : "Network\\\\Diameter",
        "path_length_mean" : "Average Path\\\\Length (Hops)",
        "bisection_bandwidth_mean" : "Total Bisection\\\\Bandwidth", 
    }
    arch_to_label = {
        "logic_and_interconnect" : "Logic on Interconnect",
        "logic_and_logic" : "Logic on Logic",
        "200" : "200mm", 
        "300" : "300mm", 
        "450" : "450mm", 
        "rectangular" : "Rec.\\mbox{\\hspace{0.2em}}",
        "maximized" : "Max.\\mbox{\\hspace{0.2em}}", 
        "baseline" : "Baseline", 
        "ours_aligned" : "Ours Aligned",
        "ours_interleaved" : "Ours Interleaved",
        "ours_rotated" : "Ours Rotated",
        "ours_contoured" : "Ours Contoured"
    }
    
    traffic_results = results.get(params_fixed["traffic"], {})
    
    # --- PASS 1: Flatten and Extract Data (Compact) ---
    all_rows = []
    r_func, s_func = params_fixed["routing_function"], params_fixed["selection_function"]

    for il, wd_dict in traffic_results.items():
        for wd, wu_dict in wd_dict.items():
            for wu, m_dict in wu_dict.items():
                for m_, res_dict in m_dict.items():
                    m = "ours_contoured" if il == "logic_and_logic" and m_ == "ours_aligned" else m_
                    res = res_dict.get(r_func, {}).get(s_func)
                    if res:
                        data = {}
                        for metric in metric_to_label:
                            if metric in res["topology_analysis"]:
                                data[metric] = res["topology_analysis"][metric]
                            elif metric in ["compute_radix"]:
                                data[metric] = {"baseline" : 4, "ours_aligned" : 4, "ours_interleaved" : 4, "ours_rotated" : 7, "ours_contoured" : 5}[m]
                            elif metric in ["interconnect_radix"]:
                                if il == "logic_and_logic":
                                    data[metric] = "-"
                                else:
                                    data[metric] = {"baseline" : 4, "ours_aligned" : 6, "ours_interleaved" : 6, "ours_rotated" : 7}[m]
                        all_rows.append({"il": il, "wd": str(wd), "wu": wu, "m": m, "data": data, "il_span": 0, "wd_span": 0, "wu_span": 0})

    # --- PASS 2: Calculate Multirow Spans (Compact) ---
    for i, row in enumerate(all_rows):
        # IL Span
        if i == 0 or row["il"] != all_rows[i-1]["il"]:
            span = 1; j = i + 1
            while j < len(all_rows) and all_rows[j]["il"] == row["il"]: span += 1; j += 1
            row["il_span"] = span
        
        # WD Span
        if i == 0 or row["il"] != all_rows[i-1]["il"] or row["wd"] != all_rows[i-1]["wd"]:
            span = 1; j = i + 1
            while j < len(all_rows) and all_rows[j]["il"] == row["il"] and all_rows[j]["wd"] == row["wd"]: span += 1; j += 1
            row["wd_span"] = span

        # WU Span
        if i == 0 or row["il"] != all_rows[i-1]["il"] or row["wd"] != all_rows[i-1]["wd"] or row["wu"] != all_rows[i-1]["wu"]:
            span = 1; j = i + 1
            while j < len(all_rows) and all_rows[j]["il"] == row["il"] and all_rows[j]["wd"] == row["wd"] and all_rows[j]["wu"] == row["wu"]: span += 1; j += 1
            row["wu_span"] = span
            
    # --- PASS 3: Generate LaTeX Table (Compact) ---
    n_metrics = len(metric_to_label)
    cols = "lll" + "c" * (1 + n_metrics)

    # Column index for the last column
    last_col_idx = 3 + n_metrics 
    
    latex_table = f"\\begin{{table}}[h]\n\\centering\n"
    latex_table += f"\\scriptsize\n"
    latex_table += f"\\setlength{{\\tabcolsep}}{{3pt}}\n"
    latex_table += f"\\caption{{Overview of key metrics for all architectures.}}\n"
    latex_table += f"\\label{{tab:overview}}\n"
    latex_table += f"\\begin{{tabular}}{{{cols}}}\n"
    latex_table += "\\toprule\n"
    
    header = "\\rotatebox{90}{Integration Level} & \\rotatebox{90}{Wafer Diameter} & \\rotatebox{90}{Wafer Utilization} & Method"
    header += " & " + " & ".join([f"\\rotatebox{{90}}{{\\makecell[l]{{{metric_to_label[m]}}}}}" for m in metric_to_label]) + " \\\\\n"
    latex_table += header
    latex_table += "\\midrule\n"
    
    for i, row in enumerate(all_rows):
        r = ""
        
        # IL, WD, WU columns with multirow logic (conditional string building)
        if row["il_span"]: r += f"\\multirow{{{row['il_span']}}}{{*}}{{\\rotatebox{{90}}{{\\makecell{{{arch_to_label[row['il']]}}}}}}}"
        
        if row["wd_span"]: r += f" & \\multirow{{{row['wd_span']}}}{{*}}{{\\rotatebox{{90}}{{\\makecell{{{arch_to_label[row['wd']]}}}}}}}"
        else: r += " & "
            
        if row["wu_span"]: r += f" & \\multirow{{{row['wu_span']}}}{{*}}{{\\rotatebox{{90}}{{\\makecell{{{arch_to_label[row['wu']]}}}}}}}"
        else: r += " & "
            
        # Method and Metrics columns (list comprehension for metrics)
        r += f" & {arch_to_label[row['m']]}"
        r += "".join([(" & " + ("%d" if type(row["data"][m]) == int else "%.2f" if type(row["data"][m]) == float else "%s")) % row["data"][m] for m in metric_to_label])
        latex_table += r + " \\\\\n"
        
        # --- Conditional \cline Logic ---
        line_command = None
        if i < len(all_rows) - 1:
            current_row, next_row = all_rows[i], all_rows[i+1]
            
            # Check for biggest break first: IL change (Full \midrule for major block break)
            if next_row["il"] != current_row["il"]:
                 line_command = f"\\cline{{1-{last_col_idx+1}}}\n"
            
            # Check for medium break: WD change (Line starts at Wafer Utilization column: Col 3)
            elif next_row["wd"] != current_row["wd"]:
                 line_command = f"\\cline{{2-{last_col_idx+1}}}\n"
                 
            # Check for smallest break: WU change (Line starts at Method column: Col 4)
            elif next_row["wu"] != current_row["wu"]:
                 line_command = f"\\cline{{3-{last_col_idx+1}}}\n"
        
        if line_command:
            latex_table += line_command
            
    latex_table += "\\bottomrule\n\\end{tabular}\n\\end{table}\n"

    
    # Save the table
    with open(f"../paper/tab/{name}_overview_table.tex", "w") as f:
        f.write(latex_table)


def create_trace_plot(results, name):
    bl_results = {}
    for integration_level in results:
        for wafer_diameter in results[integration_level]:
            for wafer_utilization in results[integration_level][wafer_diameter]:
                for method in results[integration_level][wafer_diameter][wafer_utilization]:
                    for routing_function in results[integration_level][wafer_diameter][wafer_utilization][method]:
                        for selection_function in results[integration_level][wafer_diameter][wafer_utilization][method][routing_function]:
                            res = results[integration_level][wafer_diameter][wafer_utilization][method][routing_function][selection_function]
                            if res is not None:
                                if method == "baseline":
                                    bl_results[(integration_level, wafer_diameter, wafer_utilization, routing_function, selection_function)] = res
                                # TODO: Average over all rund
                                run_idx = 0
                                if "rapidchiplet" not in res:
                                    print("No rapidchiplet results for %s, %dmm, %s, %s, %s, %s" % (integration_level, wafer_diameter, wafer_utilization, method, routing_function, selection_function))
                                    print(res)
                                run = res["rapidchiplet"]["booksim_simulation"][run_idx]["detailed"]["trace"]
                                packet_latency = run["packet_latency"]["avg"]
                                network_latency = run["network_latency"]["avg"]
                                flit_latency = run["flit_latency"]["avg"]
                                packet_injection_rate = run["injected_packet_rate"]["avg"]
                                flit_injection_rate = run["injected_flit_rate"]["avg"]
                                packt_size = run["injected_packet_size"]["avg"]
                                hops = run["hops"]["avg"]
                                runtime = run["total_run_time"]
                                #packets_sim = run["total_trace_packets"]
                                packets_sim = 0
                                hlp.print_cyan("Results for %s, %dmm, %s, %s, %s, %s:" % (integration_level, wafer_diameter, wafer_utilization, method, routing_function, selection_function))
                                hlp.print_green("Pkt Lat: %.2f | Flt Lat: %.2f | Net Lat: %.2f | Pkt Inj Rate: %.4f | Flt Inj Rate: %.4f | Pkt Size: %.2f | Hops: %.2f | Run Time: %.2f s | Pkts Sim: %d" % (packet_latency, flit_latency, network_latency, packet_injection_rate, flit_injection_rate, packt_size, hops, runtime, packets_sim))
                                bl_res = bl_results.get((integration_level, wafer_diameter, wafer_utilization, routing_function, selection_function))
                                if bl_res is not None and method != "baseline":
                                    bl_run = bl_res["rapidchiplet"]["booksim_simulation"][run_idx]["detailed"]["trace"]
                                    packet_lat_rel = 100 * (packet_latency / bl_run["packet_latency"]["avg"] - 1)
                                    network_lat_rel = 100 * (network_latency / bl_run["network_latency"]["avg"] - 1)
                                    flit_lat_rel = 100 * (flit_latency / bl_run["flit_latency"]["avg"] - 1)
                                    packet_inj_rate_rel = 100 * (packet_injection_rate / bl_run["injected_packet_rate"]["avg"] - 1)
                                    flit_inj_rate_rel = 100 * (flit_injection_rate / bl_run["injected_flit_rate"]["avg"] - 1)
                                    packt_size_rel = 100 * (packt_size / bl_run["injected_packet_size"]["avg"] - 1)
                                    hops_rel = 100 * (hops / bl_run["hops"]["avg"] - 1)
                                    runtime_rel = 100 * (runtime / bl_run["total_run_time"] - 1)
                                    #packets_sim_rel = 100 * (packets_sim / bl_run["total_trace_packets"] - 1)
                                    packets_sim_rel = 0
                                    hlp.print_yellow("Rel to Baseline -> Pkt Lat: %.2f%% | Flt Lat: %.2f%% | Net Lat: %.2f%% | Pkt Inj Rate: %.2f%% | Flt Inj Rate: %.2f%% | Pkt Size: %.2f%% | Hops: %.2f%% | Run Time: %.2f%% | Pkts Sim: %.2f%%" % (packet_lat_rel, flit_lat_rel, network_lat_rel, packet_inj_rate_rel, flit_inj_rate_rel, packt_size_rel, hops_rel, runtime_rel, packets_sim_rel)) 




                



if __name__ == "__main__":
    # Read command line arguments

    if "-h" in sys.argv or "--help" in sys.argv:
        print("Usage: python plots.py [options]")
        print("Options:")
        print("  --sys         Create system visualizations for all designs")
        print("  --topo        Create topology visualizations for all designs")
        print("  --rcvbs      Create RapidChiplet vs BookSim comparison plot")
        print("  --corr       Create correlation analysis plot")
        print("  --spa        Create sample period analysis plot")
        print("  --vba        Create VC buffer analysis plot")
        print("  --heatmap    Create heatmap vs baseline plots for latency, throughput, area and power")
        print("  --pld        Create path length distribution plots for all architectures")
        print("  --lvl        Create latency vs load plots for all architectures")
        print("  --apb        Create area and power breakdown plots for all architectures")
        print("  --ot         Create overview table summarizing architecture metrics")
        print("  --pa         Create power analysis plots for all architectures")
        print("  --aa         Create area analysis plots for all architectures")
        print("  --tra        Create trace plots for all architectures")
        sys.exit(0)

    system_plot = "--sys" in sys.argv
    topology_plot = "--topo" in sys.argv
    rapidchiplet_vs_booksim_plot = "--rcvbs" in sys.argv
    correlation_analysis_plot = "--corr" in sys.argv
    sample_period_analysis_plot = "--spa" in sys.argv
    vc_buffer_analysis_plot = "--vba" in sys.argv
    heatmap_vs_baseline_plot = "--heatmap" in sys.argv
    path_length_distribution_plot = "--pld" in sys.argv
    latency_vs_load_plot = "--lvl" in sys.argv
    area_and_power_breakdown_plot = "--apb" in sys.argv
    overview_table = "--ot" in sys.argv
    power_analysis = "--pa" in sys.argv
    area_analysis = "--aa" in sys.argv
    trace_plot = "--tra" in sys.argv

    # Get experiment
    experiment = cfg.experiment
    # Create a list of all designs (all combinations of experiment parameters)
    designs = [{}]
    for key in experiment.keys():
        new_designs = []
        for design in designs:
            for value in experiment[key]:
                new_design = cpy.deepcopy(design)
                new_design[key] = value
                new_designs.append(new_design)
        designs = new_designs
    # Remove designs that are not valid: logic_and_logic with method ours_interleaved
    designs = hlp.filter_out_invalid_designs(designs)
    # Create system and topology visualizations
    # This list stores name of plots and it is used to avoid plotting the same physical system multiple times for different logical design choices (routing function, selection function, traffic pattern)
    list_of_plot_names = []
    if system_plot or topology_plot:
        for design in designs:
            name = "%s_%dmm_%s_%s" % (design["integration_level"], design["wafer_diameter"], design["wafer_utilization"], design["method"]) 
            if name not in list_of_plot_names:
                list_of_plot_names.append(name)
                hlp.print_cyan("Constructing system for design %s" % name)
                system = run_exp.construct_system_for_single_design(design, cfg.parameters)
                if system_plot:
                    hlp.print_cyan("Visualizing system for design %s" % name)
                    system.visualize(name + "_system")
                if topology_plot:
                    do_shift = ((design["integration_level"] == "logic_and_logic") and ("ours" in design["method"])) or ((design["integration_level"] == "logic_and_interconnect") and (design["method"] == "ours_rotated"))
                    hlp.print_cyan("Visualizing topology for design %s" % name)
                    visualize_network_topology(system, name, do_shift=do_shift)
    # Read results
    results = {}
    if (rapidchiplet_vs_booksim_plot or correlation_analysis_plot or sample_period_analysis_plot or vc_buffer_analysis_plot or heatmap_vs_baseline_plot or path_length_distribution_plot or latency_vs_load_plot or area_and_power_breakdown_plot or overview_table or power_analysis or area_analysis or trace_plot):
        hlp.print_cyan("Reading all results")
        results = read_all_results(experiment)
    # RapidChiplet vs BookSim comparison plot (not used for paper)
    if rapidchiplet_vs_booksim_plot:
        hlp.print_cyan("Plotting RapidChiplet vs BookSim comparison")
        plot_rapidchiplet_vs_booksim(results, "all_designs")
    # Correlation analysis plot (not used for paper)
    if correlation_analysis_plot:
        hlp.print_cyan("Plotting correlation analysis")
        plot_correlation_analysis(results, "all_designs")
    # Sample period analysis plot (not used for paper; done in advance of a subset of designs)
    if sample_period_analysis_plot:
        hlp.print_cyan("Plotting sample period analysis")
        plot_sample_period_analysis(results, "all_designs")
    # VC buffer analysis plot (not used for paper; done in advance of a subset of designs)
    if vc_buffer_analysis_plot:
        hlp.print_cyan("Plotting VC buffer analysis")
        plot_vc_buffer_analysis(results, "all_designs")
    # Heatmap vs baseline plots (used in paper)
    if heatmap_vs_baseline_plot:
        for integration_level in experiment["integration_level"]:
            for traffic in [x for x in cfg.experiment["traffic"] if not x.startswith("trace")]:
                for metric in ["latency", "throughput", "energy"]:
                    hlp.print_cyan("Plotting heatmap vs baseline for architecture %s, traffic %s, metric %s" % (integration_level, traffic, metric))
                    name = "%s_%s" % (integration_level, traffic)
                    results_subset = results[traffic][integration_level]
                    # For logic_and_logic, only keep baseline and ours_aligned methods for the heatmap vs baseline plot
                    if integration_level == "logic_and_logic":
                        filtered_results = {}
                        for wd in results_subset:
                            filtered_results[wd] = {}
                            for wu in results_subset[wd]:
                                filtered_results[wd][wu] = {}
                                for method in results_subset[wd][wu]:
                                    if method in ["baseline", "ours_aligned"]:
                                        filtered_results[wd][wu][method] = results_subset[wd][wu][method]
                        results_subset = filtered_results
                    plot_heatmap_vs_baseline(results_subset, metric, name)
    # Area analysis plot (used for paper)
    if area_analysis:
        for integration_level in experiment["integration_level"]:
            wafer_diameter = 300 # Same for all wafer diameters in the paper
            traffic = "uniform" # Same for all traffic patterns in the paper
            wafer_utilization = "rectangular" # Same for all wafer utilizations in the paper
            results_subset = results[traffic][integration_level][wafer_diameter][wafer_utilization]
            name = integration_level
            hlp.print_cyan("Plotting area analysis for architecture %s" % (name))
            plot_area_analysis(results_subset, name)

    # Iterate through designs
    if (path_length_distribution_plot or latency_vs_load_plot or area_and_power_breakdown_plot or power_analysis):
        for integration_level in experiment["integration_level"]:
            for wafer_diameter in experiment["wafer_diameter"]:
                for wafer_utilization in experiment["wafer_utilization"]:
                    for traffic in [x for x in cfg.experiment["traffic"] if not x.startswith("trace")]:
                        results_subset = results[traffic][integration_level][wafer_diameter][wafer_utilization]
                        # For logic_and_logic, only keep baseline and ours_aligned methods
                        if integration_level == "logic_and_logic":
                            filtered_results = {}
                            for method in results_subset:
                                if method in ["baseline", "ours_aligned"]:
                                    filtered_results[method] = results_subset[method]
                            results_subset = filtered_results
                        name = "%s_%dmm_%s_%s" % (integration_level, wafer_diameter, wafer_utilization, traffic)
                        # Path length distribution plot (not used for paper - this only compare raw shortest paths without considering any turn restrictions for deadlock avoidance)
                        if path_length_distribution_plot:
                            hlp.print_cyan("Plotting path length distribution for architecture %s" % name)
                            plot_path_length_distribution(results_subset, name)
                        # Latency vs load plot (used for paper)
                        if latency_vs_load_plot:
                            hlp.print_cyan("Plotting latency vs load for architecture %s and traffic pattern %s" % (name, traffic))
                            plot_latency_vs_load(results_subset, name)
                        # Power analysis plot (used for paper)
                        if power_analysis:
                            hlp.print_cyan("Plotting power analysis for architecture %s and traffic pattern %s" % (name, traffic))
                            plot_power_analysis(results_subset, name)
                        # Area and power breakdown plot (not for paper)
                        if area_and_power_breakdown_plot:
                            hlp.print_cyan("Plotting area and power breakdown for architecture %s and traffic pattern %s" % (name, traffic))
                            for technology in ["45nm", "7nm"]:
                                for mode in ["saturation throughput", "highest common throughput"]:
                                    plot_area_and_power_brakdown(results_subset, name, technology, mode)

    # Trace plot
    if trace_plot:
        for traffic in [x for x in cfg.experiment["traffic"] if x.startswith("trace")]:
            for integration_level in experiment["integration_level"]:
                results_subset = results[traffic][integration_level]
                name = traffic + "_" + integration_level
                hlp.print_cyan("Creating trace plot for trace %s and integration level %s" % (traffic, integration_level))
                # For logic_and_logic, only keep baseline and ours_aligned methods for the heatmap vs baseline plot
                if integration_level == "logic_and_logic":
                    filtered_results = {}
                    for wd in results_subset:
                        filtered_results[wd] = {}
                        for wu in results_subset[wd]:
                            filtered_results[wd][wu] = {}
                            for method in results_subset[wd][wu]:
                                if method in ["baseline", "ours_aligned"]:
                                    filtered_results[wd][wu][method] = results_subset[wd][wu][method]
                    results_subset = filtered_results
                plot_heatmap_vs_baseline(results_subset, "trace-latency", name)

    # Overview table (not used for paper)
    if overview_table:
        hlp.print_cyan("Creating overview table")
        create_overview_table(results, "all_designs")
