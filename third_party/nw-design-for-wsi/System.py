# Python modules
from typing import List
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle

# Custom modules
from Wafer import Wafer
import config as cfg
import helpers as hlp

class System:
    """A class to represent a system containing multiple wafers.
    Attributes:
        wafers (List[Wafer]): A list of Wafer objects contained in the system.
    """
    def __init__(self, wafers : List[Wafer], integration_level : str, wafer_diameter : int, wafer_utilization : str, method : str, routing_function : str, selection_function : str, traffic : str):
        self.wafers = wafers
        self.integration_level = integration_level
        self.wafer_diameter = wafer_diameter
        self.wafer_utilization = wafer_utilization
        self.method = method
        self.traffic = traffic
        self.routing_function = routing_function
        self.selection_function = selection_function

    def visualize(self, name : str, show_global_reticle_ids : bool = False, show_reticle_attribute : str = ""):
        fig, ax = plt.subplots(1, 1 + len(self.wafers), figsize=(5 * (1 + len(self.wafers)), 5))
        # If we show the global reticle IDs, set set them as reticle attributes and we overwrite the attribute_to_show parameter
        if show_global_reticle_ids:
            if not all(["global_reticle_id" in reticle.attributes for wafer in self.wafers for reticle in wafer.reticles]):
                hlp.register_error("Not all reticles have a global_reticle_id attribute. Please run add_global_reticle_ids(system) first.")
            attribute_to_show = "global_reticle_id"
        # Visualize each wafer
        for layer, wafer in enumerate(self.wafers):
            wafer.add_to_visualization(ax = ax[0], show_local_reticle_ids = False, show_reticle_attribute = show_reticle_attribute, layer = layer)
            wafer.add_to_visualization(ax = ax[layer + 1], show_local_reticle_ids = False, show_reticle_attribute = show_reticle_attribute, layer = layer)
        # Set the title and labels
        for i in range(len(self.wafers) + 1):
            ax[i].set_title("System Overview" if i == 0 else f"Wafer {i-1}", fontsize=16)
            max_wafer_diameter = max(wafer.diameter for wafer in self.wafers)
            ax[i].set_xlim(-max_wafer_diameter/2 - 33, max_wafer_diameter/2 + 33)
            ax[i].set_ylim(-max_wafer_diameter/2 - 33, max_wafer_diameter/2 + 33)
            ax[i].set_aspect('equal', adjustable='box')
        plt.savefig("plots/" + name + "." + cfg.plot_format, dpi=cfg.plot_dpi)
        plt.close(fig)



