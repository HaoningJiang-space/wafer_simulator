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


def perform_sample_period_analysis(system : System, name : str) -> Dict:
    # Run the analyse_topology function to compute the network information
    at.analyze_topology(system)
    # Double sample period and run BookSim until sample period exceeds 100000
    sample_period = 16
    results = {}
    while sample_period <= 100000: 
        hlp.print_cyan(f"Running sample period analysis with sample period {sample_period}...")
        # Export the system to RapidChiplet
        rc_inputs = erc.export_system_to_rapidchiplet(cpy.deepcopy(system), name + "_spa", bs_params = {"sample_period": sample_period, "repetitions" : 3, "precision" : 0.001}) 
        # Run RapidChiplet
        res = rrc.run_rapidchiplet(rc_inputs, ["booksim_simulation"], name + "_spa", verbose = True)
        # Update results
        results[sample_period] = {"rapidchiplet" : res}
        # Update sample period
        sample_period *= 2
    # Return results
    return results




