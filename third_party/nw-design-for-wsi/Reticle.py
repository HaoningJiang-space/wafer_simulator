# Python modules
import math
from typing import List, Tuple
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
from matplotlib.patches import Polygon as mpl_Polygon
from shapely.geometry import Polygon, box

# Custom modules
from VerticalConnector import VerticalConnector
import helpers as hlp
import config as cfg

class Reticle:
    def __init__(self, x : float, y : float, typ : str, shape_points : List[Tuple[float,float]], vertical_connectors : List[VerticalConnector], noc_topology : str):
        """Initialize a reticle object.
        Args:
            x (float): x-coordinate of the reticle's center w.r.t the wafer center.
            y (float): y-coordinate of the reticle's center w.r.t the wafer center.
            w (float): width of the reticle.
            h (float): height of the reticle.
            typ (str): type of the reticle, must be one of 'compute', 'interconnect', 'memory', or 'io'.
            vertical_connectors (List[VerticalConnector]): List of vertical connectors of reticle. The index in the list is the id of the vertical connector.
            noc_topology (str): Type of NoC topology used in the reticle, either "central_router", "fully_connected" or "concentration_2"
        """
        # Set location and shape points
        self.x = x
        self.y = y
        self.shape_points = [(x + p[0], y + p[1]) for p in shape_points]
        # Validate and set the type
        if typ in ['compute', 'interconnect', 'memory', 'io']:
            self.typ = typ
        else:
            hlp.register_error('Reticle type must be one of: compute, interconnect, memory, io')
        # Validate and set the NoC topology
        if noc_topology in ["central_router", "fully_connected", "concentration_2"]:
            self.noc_topology = noc_topology
        else:
            hlp.register_error('NoC topology must be one of: central_router, fully_connected, concentration_2')
        # Move and validate and set the vertical connectors. If valid, set them
        for vc in vertical_connectors:
            vc.x += x
            vc.y += y
        for vcid1, vc1 in enumerate(vertical_connectors):
            # Check for overlap with other vertical connectors
            for vcid2 in range(vcid1 + 1, len(vertical_connectors)):
                if vc1.overlaps(vertical_connectors[vcid2]):
                    hlp.register_error(f'Overlapping vertical connectors with ids {vcid1} and {vcid2}')
            # Check if the vertical connector is within the reticle bounds
            # Note that the center of the vertical connector is given as coordinates w.r.t. the center of the reticle
            if not self.contains_vc(vc1):
                # This yields errors due to numerical imprecision in some cases - remove this check for now and check manually in the system visualization
                #hlp.register_error(f'Vertical connector with id {vcid1} is not within the reticle bounds')
                pass
        self.vertical_connectors = vertical_connectors
        # Compute width and height based on shape points
        self.w = max(p[0] for p in self.shape_points) - min(p[0] for p in self.shape_points)
        self.h = max(p[1] for p in self.shape_points) - min(p[1] for p in self.shape_points)
        # This can be used to store additional attributes such as neighbors, etc.
        self.attributes = {}

    def overlaps(self, other: "Reticle") -> bool:
        """Check if this reticle overlaps with another reticle (polygons).
        Args:
            other (Reticle): The other reticle to check for overlap.
        Returns:
            bool: True if the reticles overlap, False otherwise.
        """
        poly_self = Polygon(self.shape_points)
        poly_other = Polygon(other.shape_points)
        return poly_self.overlaps(poly_other)

    def contains_vc(self, vc: VerticalConnector) -> bool:
        poly = Polygon(self.shape_points)
        rect = box(vc.x - vc.w/2, vc.y - vc.h/2, vc.x + vc.w/2, vc.y + vc.h/2)
        return rect.within(poly)

    def is_in_wafer(self, wafer_diameter: float) -> bool:
        """Check if the reticle is within the wafer bounds.
        Args:
            wafer_diameter (float): Diameter of the wafer.
        Returns:
            bool: True if the reticle is within the wafer bounds, False otherwise.
        """
        return all(x**2 + y**2 <= (wafer_diameter / 2)**2 for (x, y) in self.shape_points)

    def enclosing_rectangle_is_in_wafer(self, wafer_diameter: float) -> bool:
        """Check if the reticle's enclosing rectangle is within the wafer bounds.
        Args:
            wafer_diameter (float): Diameter of the wafer.
        Returns:
            bool: True if the reticle's enclosing rectangle is within the wafer bounds, False otherwise.
        """
        minx = min(p[0] for p in self.shape_points)
        maxx = max(p[0] for p in self.shape_points)
        miny = min(p[1] for p in self.shape_points)
        maxy = max(p[1] for p in self.shape_points)
        corners = [(minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy)]
        return all(x**2 + y**2 <= (wafer_diameter / 2)**2 for (x, y) in corners)

    def get_area(self) -> float:
        """Calculate the area of the reticle based on its shape points.
        Returns:
            float: Area of the reticle.
        """
        poly = Polygon(self.shape_points)
        return poly.area

    def add_to_visualization(self, ax, show_vc_ids : bool = False, show_reticle_attribute : str = "", layer : int = 0):
        """ Add the reticle and its vertical connectors to the given matplotlib axis.
            Args:
            ax (matplotlib.axes.Axes): The axis to which the reticle and vertical connectors will be added.
            show_vc_ids (bool): If True, display the IDs of the vertical connectors.
            show_reticle_ids (bool): If True, display the ID of the reticle.
            show_reticle_attribute (str): If provided, display the value of this attribute for the
        """
        col = cfg.reticle_color_by_layer[str((2 * layer) % len(cfg.reticle_color_by_layer))]
        dcol = hlp.darken(col, factor=0.7)
        z_ret = 10 * layer + 1
        z_link = 10 * layer + 2
        z_router = 10 * layer + 3
        z_vc = 10 * layer + 4
        z_vc_dot = 10 * layer + 5
        # Visualize the reticle outline
        poly = mpl_Polygon(self.shape_points, closed=True, facecolor=col + "33", edgecolor=col, linewidth=0.75, zorder=z_ret)
        ax.add_artist(poly)
        # Show reticle attribute if specified
        if show_reticle_attribute != "":
            if show_reticle_attribute in self.attributes:
                val = self.attributes[show_reticle_attribute]
                val = round(val, 2) if isinstance(val, float) else val
                ax.text(self.x, self.y, str(val), color='black', fontsize=6, ha='center', va='center')
            else:
                hlp.register_error(f'Reticle attribute \"{show_reticle_attribute}\" not found in reticle attributes.')
        # Visualize the NoC topology if applicable
        if self.noc_topology == "central_router":
            rad = (self.w + self.h) / 50
            circ = Circle((self.x, self.y), rad, color = dcol, fill=True, zorder=z_router)
            ax.add_patch(circ)
            for vc in self.vertical_connectors:
                ax.plot([self.x, vc.x], [self.y, vc.y], color=dcol, linewidth=0.5, zorder=z_link)
        elif self.noc_topology == "fully_connected":
            for i in range(len(self.vertical_connectors)):
                for j in range(i + 1, len(self.vertical_connectors)):
                    vc1 = self.vertical_connectors[i]
                    vc2 = self.vertical_connectors[j]
                    ax.plot([vc1.x, vc2.x], [vc1.y, vc2.y], color=dcol, linewidth=0.5, zorder=z_link)
        elif self.noc_topology == "concentration_2":
            vc_coords = [(vc.x, vc.y) for vc in self.vertical_connectors]
            router_coords = hlp.pair_closest(vc_coords)
            rad = (self.w + self.h) / 50
            # Draw links between routers
            for i in range(len(router_coords)):
                for j in range(i + 1, len(router_coords)):
                    (x1a, y1a), (x2a, y2a) = router_coords[i]
                    (x1b, y1b), (x2b, y2b) = router_coords[j]
                    ax.plot([(x1a+x2a)/2, (x1b+x2b)/2], [(y1a+y2a)/2, (y1b+y2b)/2], color=dcol, linewidth=0.5, zorder=z_link)
            # Draw routers
            for ((x1, y1),(x2,y2)) in router_coords:
                circ = Circle(((x1+x2)/2, (y1+y2)/2), rad, color = dcol, fill=True, zorder=z_router)
                ax.add_patch(circ)
                # Attach links to VCs
                ax.plot([x1, (x1+x2)/2], [y1, (y1+y2)/2], color= dcol, linewidth=0.5, zorder=z_link)
                ax.plot([x2, (x1+x2)/2], [y2, (y1+y2)/2], color= dcol, linewidth=0.5, zorder=z_link)
        # Visualize the vertical connectors
        for (vc_id, vc) in enumerate(self.vertical_connectors):
            rect = Rectangle((vc.x - vc.w/2, vc.y - vc.h/2), vc.w, vc.h, edgecolor="#000000", facecolor=col + "66", linewidth=0.1, zorder=z_vc)
            ax.add_patch(rect)
            if show_vc_ids:
                ax.text(vc.x, vc.y, str(vc_id), color='black', fontsize=8, ha='center', va='center')
            rad = 1.15
            circ = Circle((vc.x, vc.y), rad, color = "#000000", fill=True, zorder=z_vc_dot, linewidth=0)
            ax.add_patch(circ)


    def visualize(self, name : str, show_vc_ids : bool = False):
        """ Visualize the reticle and its vertical connectors.
            Args:
            name (str): Name of the plot file to save.
        """ 
        fig, ax = plt.subplots()
        self.add_to_visualization(ax=ax, show_vc_ids=show_vc_ids)
        minx, maxx = min(p[0] for p in self.shape_points), max(p[0] for p in self.shape_points)
        miny, maxy = min(p[1] for p in self.shape_points), max(p[1] for p in self.shape_points)
        ax.set_xlim(minx - 1, maxx + 1)
        ax.set_ylim(miny - 1, maxy + 1)
        ax.set_aspect('equal', adjustable='box')
        plt.savefig("plots/" + name + "." + cfg.plot_format, dpi=cfg.plot_dpi)
        plt.close(fig)

def create_reticle(x : float, y : float, w : float, h : float, typ : str, shape : str, shape_param : float, vc_placement : str, vc_size : Tuple[float, float]) -> Reticle:
    """Create a reticle with specific vertical connector placement.
    Args:
        x (float): x-coordinate of the reticle's center w.r.t the wafer center.
        y (float): y-coordinate of the reticle's center w.r.t the wafer center.
        w (float): width of the reticle.
        h (float): height of the reticle.
        typ (str): type of the reticle, must be one of 'compute', 'interconnect', 'memory', or 'io'.
        vc_placement (str): placement of vertical connectors, must be one of 'corners' or 'left-right'.
        vc_size (Tuple[float, float]): size of the vertical connectors as a tuple (width, height).
    Returns:
        Reticle: A reticle object with the specified parameters.
    """
    # Create the shape points based on the shape
    shape_points = []
    if shape == "rectangular":
        shape_points = [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]
    elif shape == "H":
        a = shape_param
        b = h / 4
        shape_points = [(-w/2,-h/2),(w/2,-h/2),(w/2,-h/2+b),(w/2-a,-h/2+b),(w/2-a,h/2-b),(w/2,h/2-b),(w/2,h/2),(-w/2,h/2),(-w/2,h/2-b),(-w/2+a,h/2-b),(-w/2+a,-h/2+b),(-w/2,-h/2+b)]
    elif shape == "plus":
        a = shape_param
        b = h / 4
        shape_points = shape_points = [(-w/2,-b),(-w/2+a,-b),(-w/2+a,-h/2),(w/2-a,-h/2),(w/2-a,-b),(w/2,-b),(w/2,b),(w/2-a,b),(w/2-a,h/2),(-w/2+a,h/2),(-w/2+a,b),(-w/2,b)]
    elif shape == "rotated_45":
        custom_w = 22.9 # Precise: 22.980970388562795
        custom_h = 32.5 # Precise: 32.52883336364832
        hw, hh = custom_w / 2, custom_h / 2
        th = math.radians(45)
        c, s = math.cos(th), math.sin(th)
        shape_points = [(-hw * c + hh * s, -hw * s - hh * c),( hw * c + hh * s,  hw * s - hh * c),( hw * c - hh * s,  hw * s + hh * c),(-hw * c - hh * s, -hw * s + hh * c)]
    else:
        hlp.register_error(f'Invalid shape \"{shape}\".')
    # Create the placement of the vertical connectors based on the vc_placement
    vc_w, vc_h = vc_size
    vertical_connectors = []
    if vc_placement == "corners":
        vc_top_left = VerticalConnector(-w/2 + vc_w / 2, h/2 - vc_h / 2, vc_w, vc_h)
        vc_top_right = VerticalConnector(w/2 - vc_w / 2, h/2 - vc_h / 2, vc_w, vc_h)
        vc_bottom_left = VerticalConnector(-w/2 + vc_w / 2, -h/2 + vc_h / 2, vc_w, vc_h)
        vc_bottom_right = VerticalConnector(w/2 - vc_w / 2, -h/2 + vc_h / 2, vc_w, vc_h)
        vertical_connectors = [vc_top_left, vc_top_right, vc_bottom_left, vc_bottom_right]
    elif vc_placement == "left-right":
        vc_top_left_1 = VerticalConnector(-w/2 + vc_w / 2, h/2 - vc_h / 2, vc_w, vc_h)
        vc_top_left_2 = VerticalConnector(-w/2 + 1.5 * vc_w, h/2 - vc_h * 1.5, vc_w, vc_h)
        vc_top_right_1 = VerticalConnector(w/2 - vc_w / 2, h/2 - vc_h / 2, vc_w, vc_h)
        vc_top_right_2 = VerticalConnector(w/2 - 1.5 * vc_w, h/2 - vc_h * 1.5, vc_w, vc_h)
        vc_bottom_left_1 = VerticalConnector(-w/2 + vc_w / 2, -h/2 + vc_h / 2, vc_w, vc_h)
        vc_bottom_left_2 = VerticalConnector(-w/2 + 1.5 * vc_w, -h/2 + vc_h * 1.5, vc_w, vc_h)
        vc_bottom_right_1 = VerticalConnector(w/2 - vc_w / 2, -h/2 + vc_h / 2, vc_w, vc_h)
        vc_bottom_right_2 = VerticalConnector(w/2 - 1.5 * vc_w, -h/2 + vc_h * 1.5, vc_w, vc_h)
        vertical_connectors = [vc_top_left_1, vc_top_left_2, vc_top_right_1, vc_top_right_2, vc_bottom_left_1, vc_bottom_left_2, vc_bottom_right_1, vc_bottom_right_2]
    elif vc_placement == "edge-center":
        vc_center = VerticalConnector(0,0, vc_w, vc_h)
        vc_top_left = VerticalConnector(-w/2 + vc_w / 2, h/4 - vc_h / 2, vc_w, vc_h)
        vc_top_right = VerticalConnector(w/2 - vc_w / 2, h/4 - vc_h / 2, vc_w, vc_h)
        vc_bottom_left = VerticalConnector(-w/2 + vc_w / 2, -h/4 + vc_h / 2, vc_w, vc_h)
        vc_bottom_right = VerticalConnector(w/2 - vc_w / 2, -h/4 + vc_h / 2, vc_w, vc_h)
        vertical_connectors = [vc_center, vc_top_left, vc_top_right, vc_bottom_left, vc_bottom_right]
    elif vc_placement == "corner-center":
        vc_center = VerticalConnector(0, 0, vc_w, vc_h)
        vc_top_left = VerticalConnector(-w/2 + vc_w / 2, h/2 - vc_h / 2, vc_w, vc_h)
        vc_top_right = VerticalConnector(w/2 - vc_w / 2, h/2 - vc_h / 2, vc_w, vc_h)
        vc_bottom_left = VerticalConnector(-w/2 + vc_w / 2, -h/2 + vc_h / 2, vc_w, vc_h)
        vc_bottom_right = VerticalConnector(w/2 - vc_w / 2, -h/2 + vc_h / 2, vc_w, vc_h)
        vertical_connectors = [vc_center, vc_top_left, vc_top_right, vc_bottom_left, vc_bottom_right]
    elif vc_placement == "rotated_lower":
        if w != 26 or h != 33:
            hlp.register_error('The "rotated_lower" vertical connector placement is only defined for reticles of size 26x33mm.')
        vc_top_left = VerticalConnector(-w/2 + 1.625, h/2 - 1.625, vc_w, vc_h)
        vc_top_center_right = VerticalConnector(3.35, h/2 - 1.0, vc_w, vc_h)
        vc_top_right = VerticalConnector(w/2 - 1.625, h/2 - 1.625, vc_w, vc_h)
        vc_bottom_left = VerticalConnector(-w/2 + 1.625, -h/2 + 1.625, vc_w, vc_h)
        vc_bottom_center_left = VerticalConnector(-3.35, -h/2 + 1.0, vc_w, vc_h)
        vc_bottom_center_right = VerticalConnector(3.35, -h/2 + 1.0, vc_w, vc_h)
        vc_bottom_right = VerticalConnector(w/2 - 1.625, -h/2 + 1.625, vc_w, vc_h)
        vertical_connectors = [vc_top_left, vc_top_center_right, vc_top_right, vc_bottom_left, vc_bottom_center_left, vc_bottom_center_right, vc_bottom_right]
    elif vc_placement == "rotated_upper":
        if w != 26 or h != 33:
            hlp.register_error('The "rotated_lower" vertical connector placement is only defined for reticles of size 26x33mm.')
        vc_top = VerticalConnector(-3.35, h/2 + 1.0, vc_w, vc_h)
        vc_left_top = VerticalConnector(-w/2-1.625, 5.125, vc_w, vc_h)
        vc_left_bottom = VerticalConnector(-w/2-1.625, 1.875, vc_w, vc_h)
        vc_right_top = VerticalConnector(w/2+1.625, -1.875, vc_w, vc_h)
        vc_right_bottom = VerticalConnector(w/2+1.625, -5.125, vc_w, vc_h)
        vc_bottom_top = VerticalConnector(3.35, -h/2 + 1.0, vc_w, vc_h)
        vc_bottom_bottom = VerticalConnector(3.35, -h/2 - 1.0, vc_w, vc_h)
        vertical_connectors = [vc_top, vc_left_top, vc_left_bottom, vc_right_top, vc_right_bottom, vc_bottom_top, vc_bottom_bottom]
    elif vc_placement == "none":
        vertical_connectors = []
    else:
        hlp.register_error(f'Invalid vertical connector placement \"{vc_placement}\". Must be one of \"corners\" or \"left-right\".')
    # We set the NoC topology based on the reticle type: Compute reticles use a central router, interconnect reticles use fully connected
    noc_topology = ""
    # Compute reticles use a central router
    if typ == "compute":
        noc_topology = "central_router"
    elif typ == "interconnect":
        # Interconnect reticles of our methods use the concentration_2 topology
        if vc_placement in ["left-right", "rotated_upper"]:
            noc_topology = "concentration_2"
        # Interconnect reticles with other placements (baselines) use fully connected
        else:
            noc_topology = "fully_connected"
    else:
        hlp.register_error(f'Reticle type \"{typ}\" not supported for automatic NoC topology assignment.')
    return Reticle(x, y, typ, shape_points, vertical_connectors, noc_topology)
