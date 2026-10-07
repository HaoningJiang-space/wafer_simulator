# Python modules
import os
import concurrent.futures
import traceback
import sys
from typing import Dict, List, Callable
import copy as cpy
import builtins
import threading

# RapidChiplet modules
from rapidchiplet import run_rapidchiplet as rrc

# Custom modules
from Reticle import Reticle
from System import System
from Wafer import *
import analyze_topology as at
import export_to_rapidchiplet as erc
import export_to_orion3 as eo
import power_and_area_summary as pas
import perform_sample_period_analysis as pspa
import perform_vc_buffer_analysis as pvba


def construct_system_for_single_design(design : Dict, parameters : Dict) -> System:
    # Extract general parameters
    reticle_size = parameters["reticle_size"]
    sp = parameters["shape_param"]
    # Extract design parameters
    integration_level = design["integration_level"]
    wafer_diameter = design["wafer_diameter"]
    wafer_utilization = design["wafer_utilization"]
    method = design["method"]
    # Prepare the wafers
    wafers = []
    if integration_level == "logic_and_interconnect":
        # Compute and interconnect wafer
        if method == "baseline":
            wafers.append(create_wafer(None, wafer_diameter, "compute", reticle_size, "compute", wafer_utilization, "rectangles", {}))
            wafers.append(create_wafer(wafers[0], wafer_diameter, "interconnect", reticle_size, "interconnect", wafer_utilization, "rectangles-on-corners", {}))
        elif method == "ours_aligned":
            wafers.append(create_wafer(None, wafer_diameter, "compute", reticle_size, "compute", wafer_utilization, "rectangles_2", {}))
            wafers.append(create_wafer(wafers[0], wafer_diameter, "interconnect", reticle_size, "interconnect", wafer_utilization, "rectangles-on-edges", {"method" : "aligned", "indent": 0})) 
        elif method == "ours_interleaved":
            wafers.append(create_wafer(None, wafer_diameter, "compute", reticle_size, "compute", wafer_utilization, "rectangles_2", {}))
            wafers.append(create_wafer(wafers[0], wafer_diameter, "interconnect", reticle_size, "interconnect", wafer_utilization, "rectangles-on-edges", {"method" : "interleaved", "indent": 0})) 
        elif method == "ours_rotated":
            wafers.append(create_wafer(None, wafer_diameter, "compute", reticle_size, "compute", wafer_utilization, "rotated_lower", {}))
            wafers.append(create_wafer(wafers[0], wafer_diameter, "interconnect", reticle_size, "interconnect", wafer_utilization, "rotated_upper", {}))
        else:
            hlp.register_error("Unknown method %s not supported for integration level %s." % (method, integration_level))
    elif integration_level == "logic_and_logic": 
        k = 2  # Number of compute wafers
        for layer in range(k):
            placement = ""
            if method == "baseline":
                placement = "rectangles" if layer % 2 == 0 else "rectangles-on-corners"
            elif method == "ours_aligned":
                placement = "H-interleaved" if layer % 2 == 0 else "plus-interleaved"
            else:
                hlp.register_error("Unknown method %s not supported for integration level %s." % (method, integration_level))
            wafer_below = wafers[-1] if len(wafers) > 0 else None
            wafers.append(create_wafer(wafer_below, wafer_diameter, "compute", reticle_size, "compute", wafer_utilization, placement, {"shape_param" : sp}))
    else:
        hlp.register_error("Unknown integration level %s not supported." % integration_level)
    # Create system
    system = System(wafers, design["integration_level"], design["wafer_diameter"], design["wafer_utilization"], design["method"], design["routing_function"], design["selection_function"], design["traffic"])
    # Return system
    return system


def compute_results_for_single_system(system : System, name : str, run_rapidchiplet : bool, run_orion : bool, perform_sample_period_analysis : bool = False, perform_vc_buffer_analysis : bool = False) -> Dict:
    # Compute all results
    results = {}
    # Analyze topology - Run this before the export to RapidChiplet in order to add the require network information 
    at_results = at.analyze_topology(system)
    results["topology_analysis"] = at_results
    # Export the system to RapidChiplet
    if run_rapidchiplet:
        hlp.print_cyan(f"\nExporting system to RapidChiplet and running simulations for design: {name}")
        rc_do_compute = ["booksim_simulation"]
        rc_results = erc.run_rapidchiplet(cpy.deepcopy(system), rc_do_compute, name)
        results["rapidchiplet"] = rc_results
    # Export the system to Orion3
    if run_orion:
        hlp.print_cyan(f"\nExporting system to Orion3.0 and running simulations for design: {name}")
        orion_results = eo.run_orion3(cpy.deepcopy(system))
        results["orion3"] = orion_results
        # Compute area summary (based on the Orion3 results)
        pas.add_area_summary(results, system)
    # Compute power summary (based on the Orion3 results and RapidChiplet results )
    if run_orion and run_rapidchiplet:
        # We can only compute this for synthetic traffic patterns where we know the zero-load latency
        if not system.traffic.startswith("trace-"):
            pas.add_power_summary(results)
    # Perform sample period analysis if requested
    if perform_sample_period_analysis:
        hlp.print_cyan(f"\nPerforming sample period analysis for design: {name}")
        spa_results = pspa.perform_sample_period_analysis(system, name)
        results["sample_period_analysis"] = spa_results
    if perform_vc_buffer_analysis:
        hlp.print_cyan(f"\nPerforming VC and buffer analysis for design: {name}")
        vcba_results = pvba.perform_vc_buffer_analysis(system, name)
        results["vc_buffer_analysis"] = vcba_results
    # Return results
    return results


def evaluate_single_design(design: Dict, parameters : Dict, use_cached_results : bool = False, run_rapidchiplet : bool = True, run_orion : bool = True, perform_sample_period_analysis : bool = False, perform_vc_buffer_analysis : bool = False, store_results : bool = True) -> Dict:
    # Print current design
    name = "%s_%dmm_%s_%s_%s_%s_%s" % (design["integration_level"], design["wafer_diameter"], design["wafer_utilization"], design["method"], design["routing_function"], design["selection_function"], design["traffic"])
    hlp.print_cyan(f"Evaluating design: {name}")
    # Construct system for the current design
    system = construct_system_for_single_design(design, parameters)
    # Set result path, load cached results if available and requested
    result_path = "results/%s_results.json" % name
    if use_cached_results and os.path.exists(result_path):
        hlp.print_cyan(f"\nLoading cached results for design: {name}")
        results = hlp.read_json(result_path)
    # If results are not cached or caching is not requested, compute results
    else:
        results = compute_results_for_single_system(system, name, run_rapidchiplet, run_orion, perform_sample_period_analysis, perform_vc_buffer_analysis)
        results["name"] = name
        results["design"] = design
        # Store the results (one file per design)
        if store_results:
            hlp.write_json(result_path, results)
    # Return results
    return results

def run_experiment(experiment : Dict, parameters : Dict, use_cached_results : bool = False, run_rapidchiplet : bool = True, run_orion : bool = True, perform_sample_period_analysis : bool = False, perform_vc_buffer_analysis : bool = False, store_results : bool = True, use_multithreading : bool = False) -> List:
    """
    Run the experiment with the given parameters.
    """
    # Construct a list of designs to evaluate
    designs = [{}]
    for key in experiment.keys():
        new_designs = []
        for design in designs:
            for value in experiment[key]:
                new_design = cpy.deepcopy(design)
                new_design[key] = value
                new_designs.append(new_design)
        designs = new_designs
    # Remove designs that are not valid (invalid): logic_and_logic with method ours_interleaved
    designs = hlp.filter_out_invalid_designs(designs)
    hlp.print_cyan(f"Total number of designs to evaluate: {len(designs)}")
    # Get number of logical cores if multithreading is enabled
    max_workers = (os.cpu_count() if use_multithreading else 1)
    # Iterate through each design
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(evaluate_single_design,design,parameters,use_cached_results,run_rapidchiplet,run_orion,perform_sample_period_analysis,perform_vc_buffer_analysis,store_results) for design in designs]
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                info = str(e) + "\n" + str(traceback.print_exc())
                hlp.register_error("Error during evaluation of a design:\n%s" % info)
    # Return results
    return results

if __name__ == "__main__":
    # Print a help message if requested
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python run_experiment.py [options]")
        print("Options:")
        print("  --use_cached_results       Use cached results if available (default: False)")
        print("  --no_rapidchiplet          Do not run RapidChiplet simulations (default: run RapidChiplet)")
        print("  --no_orion                 Do not run Orion3 simulations (default: run Orion3)")
        print("  --sample_period_analysis   Perform sample period analysis (default: False)")
        print("  --vc_buffer_analysis       Perform VC and buffer analysis (default: False)")
        print("  --no_store_results         Do not store results to files (default: store results)")
        print("  --multithreading           Enable multithreading to evaluate multiple designs in parallel (default: False)")
        sys.exit(0)

    # Check if the flag --use_cached_results argument is provided
    use_cached_results = "--use_cached_results" in sys.argv
    run_rapidchiplet = "--no_rapidchiplet" not in sys.argv
    run_orion = "--no_orion" not in sys.argv
    perform_sample_period_analysis = "--sample_period_analysis" in sys.argv
    perform_vc_buffer_analysis = "--vc_buffer_analysis" in sys.argv
    store_results = "--no_store_results" not in sys.argv
    use_multithreading = "--multithreading" in sys.argv

    # Get parameters and experiment settings form config file
    parameters = cfg.parameters
    experiment = cfg.experiment

    # Run the experiment
    results = run_experiment(experiment, parameters, use_cached_results, run_rapidchiplet, run_orion, perform_sample_period_analysis, perform_vc_buffer_analysis, store_results, use_multithreading)
