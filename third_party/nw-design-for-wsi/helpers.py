# Python modules
import os
import sys
import math
import json
import inspect
import numpy as np
from scipy import integrate

def is_float(value):
    try:
        float(value)
        return True
    except ValueError:
        return False

def write_json(filename, content):
    try:
        file = open(filename, "w")
        file.write(json.dumps(content, indent=4))
        file.close()
        return
    except Exception as e:
        print("Error writing file: %s/%s -> %s" % (os.getcwd(), filename, e))
        sys.exit(1)

def read_json(filename, suppress_errors=False):
    try:
        file = open(filename, "r")
        file_content = json.loads(file.read())
        file.close()
        return file_content
    except Exception as e:
        if not suppress_errors:
            print("Error reading file: %s/%s -> %s" % (os.getcwd(), filename, e))
        sys.exit(1)

def read_jsonl(filename):
    try:
        with open(filename, "r") as file:
            lines = [json.loads(line) for line in file if line.strip()]
        return lines
    except Exception as e:
        print("Error reading file: %s/%s -> %s" % (os.getcwd(), filename, e))
        sys.exit(1)


def register_error(msg : str) -> None:
    frame = inspect.stack()[1]
    caller_file = frame.filename.split('/')[-1]
    caller_line = frame.lineno
    caller_func = frame.function
    print_red(f"ERROR in {caller_file}:{caller_line} in {caller_func}(): {msg}")
    sys.exit(1)


def pair_closest(points):
    points = points[:]  # copy
    pairs = []

    def dist(p, q):
        return math.hypot(p[0] - q[0], p[1] - q[1])

    while len(points) > 1:
        min_d = float("inf")
        best = (0, 1)  # initialize with first valid pair

        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                d = dist(points[i], points[j])
                if d < min_d:
                    min_d = d
                    best = (i, j)

        # extract and store
        p1, p2 = points[best[0]], points[best[1]]
        pairs.append((p1, p2))

        # remove both points (pop higher index first)
        for idx in sorted(best, reverse=True):
            points.pop(idx)

    # For odd number of points, add the last one with itself
    if len(points) == 1:
        pairs.append((points[0], points[0]))

    return pairs

def red(txt : str) -> str:
    return "\33[31m%s\033[0m" % txt

def green(txt :str) -> str:
    return "\33[32m%s\033[0m" % txt 

def magenta(txt : str) -> str:
    return "\33[35m%s\033[0m" % txt

def blue(txt : str) -> str:
    return "\33[34m%s\033[0m" % txt

def yellow(txt : str) -> str:
    return "\33[33m%s\033[0m" % txt

def cyan(txt : str) -> str:
    return "\33[36m%s\033[0m" % txt

def print_red(txt : str) -> None:
    print(red(txt))

def print_green(txt :str) -> None:
    print(green(txt))

def print_magenta(txt : str) -> None:
    print(magenta(txt))

def print_blue(txt : str) -> None:
    print(blue(txt))

def print_yellow(txt : str) -> None:
    print(yellow(txt))

def print_cyan(txt : str) -> None:
    print(cyan(txt))

def avg_distance_to_rectangle_center(w, h):
    # integrand for first quadrant
    def integrand(y, x):
        return np.sqrt(x**2 + y**2)
    # integrate over quadrant [0, w/2] x [0, h/2]
    val, _ = integrate.dblquad(integrand,0, w/2,lambda x: 0,lambda x: h/2)
    # normalize (4 quadrants, uniform density)
    return 4 * val / (w * h)

def darken(hex_color, factor=0.7):
    """
    Darken a hex color by the given factor (0–1).
    factor=0.7 → 30% darker
    """
    # remove leading '#'
    hex_color = hex_color.lstrip('#')

    # convert hex to RGB ints
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    # apply darkening
    r = int(r * factor)
    g = int(g * factor)
    b = int(b * factor)

    # clamp to [0,255] and format back to hex
    return f"#{r:02x}{g:02x}{b:02x}"

def filter_out_invalid_designs(designs):
    valid_designs = []
    for design in designs:
        if design["integration_level"] == "logic_and_interconnect":
            if design["routing_function"] in ["shortest_path_lowest_id_first","simple_cycle_breaking_set"]:
                valid_designs.append(design)
            elif design["routing_function"] == "xy" and design["method"] in ["baseline"] and design["wafer_utilization"] in ["rectangular"]:
                valid_designs.append(design)
        elif design["integration_level"] == "logic_and_logic":
            if design["method"] in ["baseline","ours_aligned"] and design["routing_function"] in ["shortest_path_lowest_id_first","simple_cycle_breaking_set"]:
                valid_designs.append(design)
        else:
            register_error("Unknown integration level %s not supported." % design["integration_level"])
    return valid_designs



