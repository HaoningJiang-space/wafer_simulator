# Python modules

# Custom modules
import plots
import config as cfg
import helpers as hlp
import run_experiment as run_exp

# Set the plot format to pdf
cfg.plot_format = "pdf"
cfg.parameters["shape_param"] = 5

experiment = cfg.experiment




# System visualizations
"""
designs = []
# Create a list of all designs (all combinations of experiment parameters)
for il in experiment["integration_level"]:
    for m in experiment["method"]:
        if il == "logic_and_interconnect" or (il == "logic_and_logic" and m in ["baseline","ours_aligned"]):
            designs.append({"integration_level": il, "wafer_diameter" : 200, "wafer_utilization" : "maximized", "method" : m, "routing_function" : "shortest_path_lowest_id_first", "selection_function" : "random", "traffic" : "uniform"})

# Create system visualizations
for design in designs:
    name = "%s_%dmm_%s_%s" % (design["integration_level"], design["wafer_diameter"], design["wafer_utilization"], design["method"]) 
    hlp.print_cyan("Constructing system for design %s" % name)
    system = run_exp.construct_system_for_single_design(design, cfg.parameters)
    hlp.print_cyan("Visualizing system for design %s" % name)
    system.visualize(name + "_system")
"""

# Latency-vs-load, power, and area analysis for paper
tra = "randperm"
wd = 300
wu = "maximized"

results = {}

for il in cfg.experiment["integration_level"]:
    results[il] = {}
    for m in experiment["method"]:
        results[il][m] = {}
        for rf in experiment["routing_function"]:
            results[il][m][rf] = {}
            for sf in experiment["selection_function"]:
                results[il][m][rf][sf] = {}
                filename = "%s_%dmm_%s_%s_%s_%s_%s_results.json" % (il, wd, wu, m, rf, sf, tra)
                try:
                    results[il][m][rf][sf] = hlp.read_json("results/%s" % filename, suppress_errors=True)
                    hlp.print_green("Successfully read results from file results/%s." % filename)
                except:
                    results[il][m][rf][sf] = None
                    hlp.print_yellow("Warning: Could not read results from file results/%s. Skipping this design." % filename)
    # Remove invalid methods for    
    if il == "logic_and_logic":
        # Remap method name
        results[il]["ours_contoured"] = results[il].pop("ours_aligned")
        del results[il]["ours_interleaved"]
        del results[il]["ours_rotated"]

    plots.plot_power_analysis(results[il], "paper_%s" % il)
    plots.plot_area_analysis(results[il], "paper_%s" % il)
    plots.plot_latency_vs_load(results[il], "paper_%s" % il)

# Heatmap plots
results = plots.read_all_results(experiment)
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
                                method_renamed = "ours_contoured" if method == "ours_aligned" else method
                                filtered_results[wd][wu][method_renamed] = results_subset[wd][wu][method]
                results_subset = filtered_results
            plots.plot_heatmap_vs_baseline(results_subset, metric, name)


# Trace plot
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
      plots.plot_heatmap_vs_baseline(results_subset, "trace-latency", name)

    
plots

