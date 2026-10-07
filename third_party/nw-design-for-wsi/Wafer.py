# Python modules
from typing import List, Tuple, Dict, Optional
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

# Custom modules
from Reticle import *
import helpers as hlp
import config as cfg

# A class representing a wafer with multiple reticles.
class Wafer:
    """A class representing a wafer with multiple reticles.
    Attributes:
        reticles (List[Reticle]): A list of Reticle objects placed on the wafer
        diameter (float): The diameter of the wafer
        type (str): The type of the wafer, either "compute" or "interconnect
    """
    def __init__(self, reticles : List[Reticle], diameter : float, typ : str, placement : str) -> None:
        """Initializes a Wafer object with the given reticles, diameter, and type.
        Args:
            reticles (List[Reticle]): A list of Reticle objects to be placed on the wafer. The index in the list corresponds to the reticle ID.
            diameter (float): The diameter of the wafer
            typ (str): The type of the wafer, either "compute" or "interconnect
        Raises:
            ValueError: If the reticles overlap, exceed the wafer diameter, or if the wafer type is invalid
        """
        # Set the reticles
        self.reticles = reticles
        # Set the diameter of the wafer
        self.diameter = diameter
        # Set the reticle placement
        self.placement = placement

        # Verify that the reticles are non-overlapping 
        for rid_1 in range(len(reticles)):
            for rid_2 in range(rid_1 + 1, len(reticles)):
                if reticles[rid_1].overlaps(reticles[rid_2]):
                    # This sometimes yields false positives due to floating point precision issues - remove for now and check manually 
                    # hlp.register_error(f"Reticles {rid_1} and {rid_2} overlap and cannot be placed on the same wafer.")
                    pass

        # Verify that no reticle exceeds the wafer diameter
        for rid, reticle in enumerate(reticles):
            if not reticle.is_in_wafer(diameter):
                self.visualize("debug_wafer_reticle_out_of_bounds")
                hlp.register_error(f"Reticle {rid} with position ({reticle.x}, {reticle.y}) exceeds the wafer diameter of {diameter}.")
        # Verify that the wafer type is valid and set it
        if typ in ["compute", "interconnect"]:
            self.type = typ    
        else:
            hlp.register_error(f"Invalid wafer type {typ}. Possible types are: compute, interconnect.")


    def add_to_visualization(self, ax, show_local_reticle_ids : bool = False, show_reticle_attribute : str = "", layer : int = 0) -> None:
        """ Adds the wafer and its reticles to a matplotlib Axes object for visualization.
        Args:
            ax (matplotlib.axes.Axes): The Axes object to add the wafer and ret
            show_local_reticle_ids (bool): Whether to show the reticle IDs (wafer-level) in the visualization 
            show_reticle_attribute (str): The attribute of the reticle to show in the visualization
        Returns:
            None
        """
        circ = Circle((0,0), self.diameter/2, color='black', fill=False, linewidth=1.0)
        ax.add_artist(circ)
        for (rid, reticle) in enumerate(self.reticles):
            reticle.add_to_visualization(ax = ax, show_vc_ids = False, show_reticle_attribute = show_reticle_attribute, layer = layer)
            if show_local_reticle_ids:
                ax.text(reticle.x, reticle.y, str(rid), fontsize=8, ha='center', va='center', color='black')

    def visualize(self, name : str, show_local_reticle_ids : bool = False, show_reticle_attribute : str = "") -> None:
        """ Visualizes the wafer with its reticles and saves the plot to a PDF file.
        Args:
            name (str): The name of the file to save the plot as, without the .
        Returns:
            None
        """
        fig, ax = plt.subplots()
        self.add_to_visualization(ax, show_local_reticle_ids = show_local_reticle_ids, show_reticle_attribute = show_reticle_attribute)
        # Set the title and labels
        if show_reticle_attribute:
            ax.set_title(f"System Visualization with {show_reticle_attribute} attribute")
        ax.set_xlim(-self.diameter/2 - 33, self.diameter/2 + 33)
        ax.set_ylim(-self.diameter/2 - 33, self.diameter/2 + 33)
        ax.set_aspect('equal', adjustable='box')
        plt.savefig("plots/" + name + "." + cfg.plot_format, dpi=cfg.plot_dpi)
        plt.close(fig)


def create_wafer(wafer_below : Optional[Wafer], wafer_diameter : float, wafer_type : str, reticle_size : Tuple[float,float], reticle_type : str, wafer_utilization : str, reticle_placement : str, params : Dict) -> Wafer:
    """Creates a wafer with reticles.
    Args:
        wafer_below (Wafer): An optional wafer to place the new wafer on top of. None if this is the bottom wafer.
        wafer_diameter (float): The diameter of the wafer
        wafer_type (str): The type of the wafer, either "compute" or "interconnect"
        reticle_size (Tuple[float, float]): The size of the reticle as a tuple (width, height)
        reticle_type (str): The type of the reticle, either "compute", "interconnect", "memory", or "io"
        wafer_utilization (str): The utilization of the wafer, either "rectangular" or "maximized"
        reticle_placement (str): The placement of the reticles. Options:
            - "rectangles": Place rectangular reticles on the wafer intended to use with rectangles-on-corners as 2nd layer
            - "rectangles-2": Place rectangular reticles on the wafer intended to use with rectangles-on-edges as 2nd layer
            - "rectangles-on-corners": Rectangular reticles are placed on corners of the wafer_below which has the placement "rectangular"
            - "rectangles-on-edges": Rectangular reticles are rotated by 90 degrees and placed on edges of the wafer_below which has the placement "rectangular"
            - "H-interleaved": H-shaped reticles are placed on the wafer (interleaved)
            - "plus-interleaved": Plus-shaped reticles are placed on the wafer (interleaved)
            - "rotated_lower": The lower layer of the rotated placement (non-rotated reticles)
            - "rotated_upper": The upper layer of the rotated placement (rotated reticles)

    Returns:
        Wafer: A Wafer object with the specified arrangement of reticles
    """
    ###################################################################################################
    # Verify inputs
    ###################################################################################################
    if wafer_below is not None and wafer_below.diameter != wafer_diameter:
        hlp.register_error(f"The diameter of the wafer ({wafer_diameter}) must match the diameter of the wafer below ({wafer_below.diameter}).")
    if wafer_type not in ["compute", "interconnect"]:
        hlp.register_error(f"Invalid wafer type {wafer_type}. Possible types are: compute, interconnect.")
    if reticle_size[0] <= 0 or reticle_size[1] <= 0:
        hlp.register_error(f"Invalid reticle size {reticle_size}. Reticle size must be a tuple of positive floats (width, height).")
    if reticle_type not in ["compute", "interconnect", "memory", "io"]:
        hlp.register_error(f"Invalid reticle type {reticle_type}. Possible types are: compute, interconnect, memory, io.")
    if wafer_utilization not in ["rectangular", "maximized"]:
        hlp.register_error(f"Invalid wafer utilization {wafer_utilization}. Possible utilizations are: rectangles, maximized.")
    if reticle_placement not in ["rectangles", "rectangles_2", "rectangles-on-corners", "rectangles-on-edges", "H-interleaved", "plus-interleaved", "rotated_lower", "rotated_upper"]:
        hlp.register_error(f"Invalid reticle placement {reticle_placement}. Possible placements are: rectangles, rectangles_2, rectangles-on-corners, rectangles-on-edges, H-interleaved, plus-interleaved, rotated_lower, rotated_upper.")
    if reticle_placement in ["rectangles-on-corners", "rectangles-on-edges", "rotated_upper"] and wafer_below is None:
        hlp.register_error("The reticle placement 'rectangles-on-corners', 'rotated_upper',  or 'rectangles-on-edges' requires a wafer below to place the reticles on corners or edges.")
    if reticle_placement in ["rectangles-on-corners", "rectangles-on-edges"] and wafer_below.placement not in ["rectangles", "rectangles_2"]:
        hlp.register_error(f"The wafer below must have a rectangles placement for the reticle placement '{reticle_placement}'. The wafer below has placement '{wafer_below.placement}'.")
    if reticle_placement in ["H-interleaved", "plus-interleaved"] and "shape_param" not in params:
        hlp.register_error(f"The reticle placement '{reticle_placement}' requires a 'shape_param' parameter to be specified in the params dictionary.")
    if reticle_placement == "rectangles-on-edges" and "method" not in params:
        hlp.register_error("The reticle placement 'rectangles-on-edges' requires a 'method' parameter to be specified in the params dictionary. Possible methods are: aligned and interleaved")
    if reticle_placement == "rectangles-on-edges" and "indent" not in params:
        hlp.register_error("The reticle placement 'rectangles-on-edges' requires an 'indent' parameter to be specified in the params dictionary. Possible values are: 0 or 1")
    if reticle_placement in ["rotated_lower", "rotated_upper"] and (reticle_size[0] != 26 or reticle_size[1] != 33):
        hlp.register_error(f"The reticle placement '{reticle_placement}' requires a reticle size of (26, 33). The provided reticle size is {reticle_size}.")

    ###################################################################################################
    # Variables
    ###################################################################################################
    w,h = reversed(reticle_size) if reticle_placement == "rectangles-on-edges" else reticle_size
    reticle_shape = "rectangular" if reticle_placement in ["rectangles", "rectangles_2", "rectangles-on-corners", "rectangles-on-edges", "rotated_lower"] else "H" if reticle_placement == "H-interleaved" else "plus" if reticle_placement == "plus-interleaved" else "rotated_45" if reticle_placement == "rotated_upper" else None
    sp = params["shape_param"] if reticle_placement in ["H-interleaved", "plus-interleaved"] else 0.0
    vc_placement = "corners" if reticle_placement in ["rectangles", "rectangles_2", "rectangles-on-corners"] else "left-right" if reticle_placement == "rectangles-on-edges" else "edge-center" if reticle_placement == "plus-interleaved" else "corner-center" if reticle_placement == "H-interleaved" else "rotated_lower" if reticle_placement == "rotated_lower" else "rotated_upper" if reticle_placement == "rotated_upper" else None
    vc_size = (w/2,h/2) if reticle_placement in ["rectangles", "rectangles-on-corners"] else ((h-w)/2, w/2) if reticle_placement == "rectangles_2" else ((w-h)/2, h/2) if reticle_placement == "rectangles-on-edges" else (sp, h/4) if reticle_placement in ["H-interleaved", "plus-interleaved"] else (2.0,2.0) if reticle_placement in ["rotated_lower", "rotated_upper"] else None

    ###################################################################################################
    # Find placement of reticles
    ###################################################################################################
    # Create a wafer that does not depend on the wafer_below and that uses aligned reticles
    if reticle_placement in ["rectangles", "rectangles_2","H-interleaved", "plus-interleaved", "rotated_lower"]:
        # If we use rectangular arrangement, identify largest number of rows and columns
        if wafer_utilization == "rectangular":
            # Special case for rotated placement as we need to interleave columns
            if reticle_placement == "rotated_lower":
                reticles = []
                nrows_max = int(wafer_diameter // h)
                ncols_max = int(wafer_diameter // w)
                for nrows in range(1, nrows_max + 1):
                    for ncols in range(1, ncols_max + 1):
                        for start_offset in [0,13,26]:
                            corner_ylocs = [start_offset, start_offset + nrows * h, (start_offset + (ncols - 1) * 13) % 33, (start_offset + (ncols - 1) * 13) % 33 + nrows * h]
                            center_x = ncols * w / 2
                            center_y = (max(corner_ylocs) + min(corner_ylocs)) / 2
                            reticles_tmp = []
                            for row in range(nrows):
                                for col in range(ncols):
                                    x = col * w + 0.5 * w - center_x
                                    y = (start_offset + col * 13) % 33 + row * h + 0.5 * h - center_y
                                    reticle = create_reticle(x, y, w, h, reticle_type, reticle_shape, sp, vc_placement, vc_size)
                                    reticles_tmp.append(reticle)
                                    if not reticle.enclosing_rectangle_is_in_wafer(wafer_diameter):
                                        reticles_tmp = None
                                        break
                                if not reticles_tmp:
                                    break
                            if reticles_tmp and len(reticles_tmp) > len(reticles):
                                reticles = reticles_tmp
            else:
                nrows_max = int(wafer_diameter // h)
                ncols_max = int(wafer_diameter // w)
                best_config = (0, 0)
                for nrows in range(1, nrows_max + 1):
                    for ncols in range(1, ncols_max + 1):
                        if reticle_placement in ["rectangles", "rectangles_2"]:
                            total_width = ncols * w
                            total_height = nrows * h
                        elif reticle_placement in ["H-interleaved", "plus-interleaved"]:
                            total_width = (ncols * (w-sp) + sp)
                            total_height = (nrows * h + (h/2))
                        else:
                            hlp.register_error(f"Invalid reticle placement {reticle_placement}")
                        # Check if this fits within the wafer diameter
                        if (total_width / 2)**2 + (total_height / 2)**2 <= (wafer_diameter / 2)**2:
                            if nrows * ncols > best_config[0] * best_config[1]:
                                best_config = (nrows, ncols)    
                reticles = []
                nrows, ncols = best_config
                # Create reticles based on the best configuration found
                total_width = (ncols * w) if reticle_shape == "rectangular" else (ncols * (w-sp) + sp)
                total_height = (nrows * h) if reticle_shape == "rectangular" else (nrows * h + (h/2))
                x0, y0 = -total_width / 2, -total_height / 2
                for row in range(nrows):
                    y = (row - nrows / 2 + 0.5) * h
                    for col in range(ncols):
                        if reticle_placement in ["rectangles", "rectangles_2"]:
                            x = x0 + col * w + (w/2)
                            y = y0 + row * h + (h/2)
                        elif reticle_placement in ["H-interleaved", "plus-interleaved"]:
                            x = x0 + col * (w - sp) + (w/2)
                            y = y0 + row * h + (h/2 if col % 2 == 1 else 0) + (h/2)
                        else:
                            hlp.register_error(f"Invalid reticle placement {reticle_placement}")
                        reticles.append(create_reticle(x, y, w, h, reticle_type, reticle_shape, sp, vc_placement, vc_size))
        # If we use maximized arrangement, identify the largest number of reticles that fit on the wafer, with a distinct number of reticles per row
        elif wafer_utilization == "maximized":
            # Identify the possible positions of the central reticle
            if reticle_placement in ["rectangles", "rectangles_2"]:
                start_positions = [(w/2,h/2),(0,h/2),(w/2,0),(0,0)]
            elif reticle_placement in ["H-interleaved", "plus-interleaved"]:
                start_positions = [(0,-h/4),(0,h/4),(w/2-sp/2,-h/4),(w/2-sp/2,h/4)]
            elif reticle_placement == "rotated_lower":
                # Exhaustively search all integer positions for the central reticle
                start_positions = [(x,y) for x in range(int(-w/2),int(w/2)+1,1) for y in range(int(-h/2),int(h/2)+1,1)]
            else:
                hlp.register_error(f"Invalid reticle shape {reticle_shape} for maximized wafer utilization. Possible shapes are: rectangular, H, plus.")
            # Among these positions, find the one that allows for the largest number of reticles
            reticles = []
            for start_position in start_positions:
                # For a given start position, find the number of reticles that can be placed
                positions_todo = [start_position]
                positions_done = []
                reticles_tmp = []
                while positions_todo:
                    x, y = positions_todo.pop(0)
                    positions_done.append((x, y))
                    reticle = create_reticle(x, y, w, h, reticle_type, reticle_shape, sp, vc_placement, vc_size)
                    # Check if this new reticle is within the wafer diameter
                    if reticle.enclosing_rectangle_is_in_wafer(wafer_diameter):
                        reticles_tmp.append(reticle)
                        # Identify all adjacent positions to this reticle
                        if reticle_placement in ["rectangles", "rectangles_2"]:
                            offset_to_adjacent_positions = [(w, 0), (-w, 0), (0, h), (0, -h)]
                        elif reticle_placement in ["H-interleaved", "plus-interleaved"]:
                            offset_to_adjacent_positions = [(0,h),(w-sp,h/2),(w-sp,-h/2),(0,-h),(-w+sp,-h/2),(-w+sp,h/2)]
                        elif reticle_placement == "rotated_lower":
                            offset_to_adjacent_positions = [(0,h),(w,13),(w,13-h),(0,-h),(-w,-13),(-w,h-13)]
                        # Check all adjacent positions
                        for xoff, yoff in offset_to_adjacent_positions:
                            new_position = (round(x + xoff,3), round(y + yoff,3))   # Round to avoid duplicates due to floating point precision issues
                            if new_position not in positions_done and new_position not in positions_todo:
                                positions_todo.append(new_position)
                # If this start position allows for more reticles than the previous best, update the best
                if len(reticles_tmp) > len(reticles):
                    reticles = reticles_tmp
        else:
            hlp.register_error(f"Invalid wafer utilization {wafer_utilization}. Possible utilizations are: rectangular, maximized.")
    # The upper layer of the rotated placement (rotated reticles): Reticles are placed on centers of the lower layer reticles (if they fit despite being rotated)
    elif reticle_placement == "rotated_upper":
        reticles = []
        for ret in wafer_below.reticles:
            reticle = create_reticle(ret.x, ret.y, w, h, reticle_type, reticle_shape, sp, vc_placement, vc_size)
            if reticle.is_in_wafer(wafer_diameter):
                reticles.append(reticle)
    # If we use rectangles-on-corners place the reticles based on the wafer_below
    elif reticle_placement == "rectangles-on-corners":
        reticles = []
        positions_checked = []
        for ret in wafer_below.reticles:
            positions = [(ret.x + w/2, ret.y + h/2),(ret.x - w/2, ret.y + h/2),(ret.x + w/2, ret.y - h/2),(ret.x - w/2, ret.y - h/2)]
            for pos in positions:
                if pos not in positions_checked:
                    positions_checked.append(pos)
                    reticle = create_reticle(pos[0], pos[1], w, h, reticle_type, reticle_shape, sp, vc_placement, vc_size)
                    # Check if this reticle is within the wafer diameter
                    if reticle.is_in_wafer(wafer_diameter):
                        reticles.append(reticle)
    # If we use rectangles-on-edges place the reticles based on the wafer_below
    # Note: This is the only case where width and height of the reticle_below and this reticle are swapped
    elif reticle_placement == "rectangles-on-edges":
        method = params["method"]
        indent = params["indent"]
        # Identify valid positions for interconnect reticles
        valid_positions = []
        for ret in wafer_below.reticles:
            positions = [(ret.x, ret.y + w/2), (ret.x, ret.y - w/2)]
            for pos in positions:
                if pos not in valid_positions:
                    corners = [(pos[0] + w/2, pos[1] + h/2),(pos[0] - w/2, pos[1] + h/2),(pos[0] + w/2, pos[1] - h/2),(pos[0] - w/2, pos[1] - h/2)]
                    if all((corner[0]**2 + corner[1]**2) <= (wafer_below.diameter / 2)**2 for corner in corners):
                        valid_positions.append(pos)
        # Sort positions by row and column
        positions_by_y = {}
        for pos in valid_positions:
            if pos[1] not in positions_by_y:
                positions_by_y[pos[1]] = []
            positions_by_y[pos[1]].append(pos)
        positions_by_row = []
        for y in sorted(positions_by_y.keys()):
            positions_by_row.append(sorted(positions_by_y[y], key=lambda x: x[0]))
        # Place interconnect reticles based on selected methods
        reticles = []
        if method == "aligned":
            # Create interconnect reticles with specified indent
            max_row_length = max(len(row) for row in positions_by_row)
            for row in range(len(positions_by_row)):
                start_col = (max_row_length - len(positions_by_row[row]) // 2 + indent) % 2
                for col in range(start_col, len(positions_by_row[row]), 2):
                    pos = positions_by_row[row][col]
                    reticles.append(create_reticle(pos[0], pos[1], w, h, "interconnect", reticle_shape, sp , "left-right", (vc_size[0], vc_size[1])))
        elif method == "interleaved":
            # Create interconnect reticles with alternating starting indent
            max_row_length = max(len(row) for row in positions_by_row)
            for row in range(len(positions_by_row)):
                start_col = (max_row_length - len(positions_by_row[row]) // 2 + indent) % 2
                for col in range(start_col, len(positions_by_row[row]), 2):
                    pos = positions_by_row[row][col]
                    reticles.append(create_reticle(pos[0], pos[1], w, h, "interconnect", reticle_shape, sp, "left-right", (vc_size[0], vc_size[1])))
                indent = 1 - indent
        else:
            hlp.register_error(f"Invalid method '{method}' for creating rectangles-on-edges reticles. Possible methods are: aligned, interleaved.")
    else:
        hlp.register_error(f"Invalid reticle placement {reticle_placement}. Possible placements are: rectangles, rectangles_2, rectangles-on-corners, rectangles-on-edges, H-interleaved, plus-interleaved.")
    # Create the wafer object with the reticles
    wafer = Wafer(reticles, wafer_diameter, wafer_type, reticle_placement)
    return wafer
