# Python modules
from typing import List, Tuple, Dict
import subprocess
import threading
import math
import re
import os

# Custom modules
import config as cfg
import helpers as hlp
from System import System
import analyze_topology as at

# Global lock to serialize Orion execution
# Needs to be serialized because we rewrite the config file, recompile the code and run it for each design
# NOTE: For ORION 3.0, orion_router outputs power in mW, area in um^2
_orion_lock = threading.Lock()

def export_router_to_orion(radix : int, o_params : Dict) -> None:
    orion_config = {
        "frequency" : int(cfg.network_frequency_hz),
        "radix" : radix,
        "datawidth" : int(round(cfg.link_bandwidth_bit_per_sec / cfg.network_frequency_hz)),
        "virtualchannels" : cfg.number_of_virtual_channels,
        "buffersize" : cfg.buffer_size_per_vc_flits,
    }
    # Use Orion parameters to override defaults
    for key, value in o_params.items():
        if key in orion_config:
            orion_config[key] = value
    # Paths
    orion_config_path = os.path.join(cfg.orion_path, "SIM_port.template")
    filled_in_config_path = os.path.join(cfg.orion_path, "SIM_port.h")
    # Read the template config file
    with open(orion_config_path, 'r') as f:
        orion_config_file = f.read()  # <-- single string
    # Fill in the template config file
    for key, value in orion_config.items():
        orion_config_file = orion_config_file.replace(f"<{key}>", str(value))
    # Write the filled-in config file
    with open(filled_in_config_path, 'w') as f:
        f.write(orion_config_file)

def run_orion3(system : System, o_params : Dict = {}) -> Dict:
    with _orion_lock:
        # Identify unique reticles
        unique_routers = []
        for wafer in system.wafers:
            for reticle in wafer.reticles:
                router = ("",0,0)
                if reticle.noc_topology == "central_router":
                    radix = len(reticle.vertical_connectors)
                    router = (reticle.typ, radix, 1)
                elif reticle.noc_topology == "fully_connected":
                    radix = len(reticle.vertical_connectors)
                    count = len(reticle.vertical_connectors)
                    router = (reticle.typ, radix, count)
                elif reticle.noc_topology == "concentration_2":
                    radix = int(math.ceil(len(reticle.vertical_connectors) / 2)) + 1
                    count = int(math.ceil(len(reticle.vertical_connectors) / 2))
                    router = (reticle.typ, radix, count)
                else:
                    hlp.register_error("Unsupported NoC topology '%s' for Orion3 export" % reticle.noc_topology)
                if router not in unique_routers:
                    unique_routers.append(router)
        # Compute results for each unique reticle
        orion_results = {}
        for (reticle_type, radix, count) in unique_routers:
            # Export config to Orion
            export_router_to_orion(radix, o_params)
            # Compile Orion
            subprocess.run(["make", "-B"], cwd=cfg.orion_path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Run Orion
            output = subprocess.run(["./orion_router"], cwd=cfg.orion_path, capture_output=True, text=True)
            # Collect results
            reticle_results = {}
            for line in output.stdout.splitlines():
                if ":" in line:
                    match = re.match(r"^\s*([A-Za-z0-9_]+):\s*([0-9.eE+-]+)\s*$", line)
                    if match:
                        key, value = match.groups()
                        reticle_results[key] = float(value) * count  # Scale by number of routers in reticle
            # Append results
            orion_results["%s-reticle_radix-%d" % (reticle_type, radix)] = reticle_results
    return orion_results

