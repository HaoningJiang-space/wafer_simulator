# Paths
rc_input_path = "./rapidchiplet/inputs"
orion_path = "./Orion3"

# Configuration for the wafer-scale system
router_latency_cycles = 4                       # Latency of reticle's central router in cycles (assumption)
number_of_gpcs = 8                              # Use 8 GPC (graphics processing clusters) per reticle, as in H100 / GH100
link_bandwidth_bit_per_sec = 16e12              # Each link has 2 TB/s bandwidth (same as Tesla Dojo with 2TB/s per link)
network_frequency_hz = 1e9                      # Network frequency is 1 GHz (assumption)
signal_propagation_per_cycle_mm = 2             # Signal propagation distance per cycle in mm (assumption)
number_of_virtual_channels = 1                  # Number of virtual channels per link (assumption)
buffer_size_per_vc_flits = 32                   # Buffer size per virtual channel -> Needs to be 32 for maximum performance according to VC buffer analysis.
energy_per_bit_per_mm_45nm_in_pj = 0.3          # Assumes one flipflop every 2mm. Need to change this if the signal_propagation_per_cycle_mm changes.
energy_per_bit_per_mm_7nm_in_pj = 0.1           # Assumes one flipflop every 2mm. Need to change this if the signal_propagation_per_cycle_mm changes.
area_scaling_factor_45nm_to_7nm = 0.0271        # Area scaling factor from 45nm to 7nm (based on DeepScaleTool)
area_scaling_factor_45nm_to_7nm_sram = 0.2      # Area scaling factor for SRAM from 45nm to 7nm (Assumption)
power_scaling_factor_45nm_to_7nm = 0.2473       # Power scaling factor from 45nm to 7nm (based on DeepScaleTool)

# Configuration for simulations in BookSim
bs_repetitions = 3                              # Number of repetitions for each simulation
bs_precision = 0.0001                           # Very precise, variation due to random seed is likely larger
bs_cycle_limit_for_trace_simulations = int(1e9) # Cycle limit for trace-based simulations in BookSim: Very high to avoid early stopping (will be multiplied by 1e3 in BookSim)
bs_trace_time_out = 8*60*60                     # Time-out in seconds for trace-based simulations -> 8h

# General parameters 
parameters = {}
parameters["reticle_size"] = (26.0, 33.0)   # Reticle limit in mm
parameters["shape_param"] = 0.4             # Enough hybrid bonds for a link with 2 TB/s bandwidth per direction (1GHz, 10um pitch)

# Experiment parameters: Order of keys in map and order of values in lists will define the order of experiments
experiment = {}
experiment["wafer_diameter"] = [200,300] # 300 most common, 200 in some old fabs, 450 proposed for future fabs
experiment["routing_function"] = ["simple_cycle_breaking_set"]
#experiment["traffic"] = ["trace-llama7B","uniform","randperm","neighbor","tornado"]        # NOTE: This was used for the paper, but the traces are too large for GitHub
experiment["traffic"] = ["uniform","randperm","neighbor","tornado"]
experiment["integration_level"] = ["logic_and_interconnect","logic_and_logic"]
experiment["wafer_utilization"] = ["rectangular","maximized"]
experiment["method"] = ["baseline", "ours_aligned", "ours_interleaved","ours_rotated"]
experiment["selection_function"] = ["random","adaptive"]

# Maps each system architecture to the number of GPUs that are used when collecting the respective trace on the cluster
trace_gpu_count_map = {
        ("logic_and_interconnect", 200, "rectangular") : 20,
        ("logic_and_interconnect", 200, "maximized") : 24,
        ("logic_and_interconnect", 300, "rectangular") : 48,
        ("logic_and_interconnect", 300, "maximized") : 64,
        ("logic_and_logic", 200, "rectangular") : 40,
        ("logic_and_logic", 200, "maximized") : 52,
        ("logic_and_logic", 300, "rectangular") : 96,
        ("logic_and_logic", 300, "maximized") : 124,                                                                              }

# Config for plotting
plot_format = "png"
plot_dpi = 300

# A palette of 16 colors (8 pairs) that are slightly less saturated (more pastel)
# than the previous list, maintaining the dark/light contrast.
colors = [
    # 1. Blue Pair
    "#3A4D99",  # Dark Muted Indigo
    "#82A9FF",  # Light Soft Blue

    # 2. Gold/Yellow Pair
    "#99804D",  # Dark Muted Mustard Gold
    "#FFEB85",  # Light Pale Yellow

    # 3. Green Pair
    "#407540",  # Dark Muted Pine Green
    "#99CC99",  # Light Sage Green

    # 4. Red Pair
    "#B34D4D",  # Dark Muted Rose Red
    "#FF9999",  # Light Dusty Rose

    # 5. Purple Pair
    "#8C4D8C",  # Dark Muted Amethyst
    "#CC99CC",  # Light Lilac

    # 6. Orange Pair
    "#99664D",  # Dark Muted Terra Cotta
    "#FFC299",  # Light Peach

    # 7. Cyan/Teal Pair
    "#4D7A7A",  # Dark Muted Slate Teal
    "#A3E0E0",  # Light Powder Blue/Cyan

    # 8. Brown/Tan Pair
    "#8A6E59",  # Dark Muted Taupe
    "#E0C2A3",  # Light Warm Beige
]

# Colors for reticle layers
reticle_color_by_layer = {str(i) : colors[i] for i in range(len(colors))}

# General list of markers
markers = [
    "o",   # Circle
    "s",   # Square
    "^",   # Triangle Up
    "D",   # Diamond
    "v",   # Triangle Down
    "P",   # Filled Plus (Thick Plus)
    "*",   # Star
    "X",   # Filled X (Thick X)
    "<",   # Triangle Left
    ">",   # Triangle Right
    "h",   # Hexagon 1
    "d",   # Thin Diamond
    "p",   # Pentagon
    "+",   # Plus
    "x",   # X
    "|",   # Vertical Line
]
