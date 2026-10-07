# Python modules
import numpy as np
import os
import sys
from typing import Dict
import copy as cpy

# RapidChiplet modules
from rapidchiplet import run_rapidchiplet as rrc

# Custom modules
import helpers as hlp
import plots
from Reticle import Reticle
from System import System
from Wafer import *
import analyze_topology as at
import export_to_rapidchiplet as erc
import export_to_orion3 as eo


def perform_vc_buffer_analysis(system : System, name : str) -> Dict:
    # Run the analyse_topology function to compute the network information
    at.analyze_topology(system)
    # Double buffer size and run RapidChiplet and Orion3
    buffer_size = 1
    results = {}
    while buffer_size <= 128:
        hlp.print_cyan(f"Running vc buffer analysis with buffer size {buffer_size}")
        # Export the system to RapidChiplet
        rc_inputs = erc.export_system_to_rapidchiplet(cpy.deepcopy(system), name + "_vba", bs_params = {"repetitions" : 3, "precision" : 0.001, "vc_buf_size" : buffer_size}) 
        # Run RapidChiplet
        rc_res = rrc.run_rapidchiplet(rc_inputs, ["booksim_simulation"], name + "_vba", verbose = True)
        # Run Orion3
        o_res = eo.run_orion3(system, o_params = {"buffer_size_per_vc_flits" : buffer_size})
        # Update results
        results[buffer_size] = {  "rapidchiplet": rc_res,"orion3" : o_res}
        # Update sample period
        buffer_size *= 2
    # Return results
    return results




