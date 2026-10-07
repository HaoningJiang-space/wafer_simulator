# Python libraries
import os
import sys
import json
import copy
import math
import builtins
import threading

_thread = threading.local()

def set_print_prefix(value: str) -> None:
    _thread.print_prefix = value

def get_print_prefix(default: str = "") -> str:
    return getattr(_thread, "print_prefix", default)

# Check if a string can be converted to an float
def is_float(value):
    try:
        float(value)
        return True
    except ValueError:
        return False

# Used for JSON encoding / decoding of python objects
def encode_key(key):
    if isinstance(key, tuple):
        return '__tuple__:' + json.dumps([encode_key(k) for k in key])
    return key

# Used for JSON encoding / decoding of python objects
def decode_key(key):
    if isinstance(key, str) and key.startswith('__tuple__:'):
        return tuple(decode_key(k) for k in json.loads(key[len('__tuple__:'):]))
    return key

# Used for JSON encoding / decoding of python objects
def encode_data(data):
    if isinstance(data, dict):
        return {encode_key(k): encode_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [encode_data(item) for item in data]
    elif isinstance(data, tuple):
        return {'__tuple__': True, 'items': [encode_data(item) for item in data]}
    else:
        return data

# Used for JSON encoding / decoding of python objects
def decode_data(data):
    if isinstance(data, dict):
        if '__tuple__' in data:
            return tuple(decode_data(item) for item in data['items'])
        else:
            return {decode_key(k): decode_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [decode_data(item) for item in data]
    else:
        return data

# Write a JSON file
def write_json(filename, content):
    file = open(filename, "w")
    file.write(json.dumps(encode_data(content), indent=4))
    file.close()

# Read a JSON file
def read_json(filename):
    file = open(filename, "r")
    file_content = decode_data(json.loads(file.read()))
    file.close()
    return file_content

# Write or append lines to a JSONL file
def write_or_append_jsonl(filename, data):
	mode = "a" if os.path.exists(filename) else "w"
	try:
		with open(filename, mode) as file:
			for item in data:
				file.write(json.dumps(item) + "\n")
	except Exception as e:
		print("Error writing to file: %s/%s -> %s" % (os.getcwd(), filename, e))
		sys.exit(1)


# Rotate a chiplet
def rotate_chiplet(chiplet, rotation):
    # If no rotation is needed, return chiplet as-is
    if rotation == 0:
        return chiplet
    # Rotate the chiplet if needed
    chiplet = copy.deepcopy(chiplet)
    rot = rotation // 90
    alpha = math.pi / 2 * rot
    (cx, cy) = (chiplet["dimensions"]["x"] / 2, chiplet["dimensions"]["y"] / 2)
    if rot % 2 == 1:
        chiplet["dimensions"] = {"x" : chiplet["dimensions"]["y"],"y" : chiplet["dimensions"]["x"]}
    (cxn, cyn) = (chiplet["dimensions"]["x"] / 2, chiplet["dimensions"]["y"] / 2)
    # Rotate PHYs while preserving fields
    for (pid, phy) in enumerate(chiplet.get("phys", [])):
        (x, y) = (phy["x"] - cx, phy["y"] - cy)
        (xr,yr) = (x * math.cos(alpha) - y * math.sin(alpha), x * math.sin(alpha) + y * math.cos(alpha))
        new_phy = dict(phy)
        new_phy["x"] = cxn + xr
        new_phy["y"] = cyn + yr
        chiplet["phys"][pid] = new_phy
    # Rotate TSVs while preserving fields
    if "tsvs" in chiplet:
        for (tid, tsv) in enumerate(chiplet.get("tsvs", [])):
            (x, y) = (tsv["x"] - cx, tsv["y"] - cy)
            (xr,yr) = (x * math.cos(alpha) - y * math.sin(alpha), x * math.sin(alpha) + y * math.cos(alpha))
            new_tsv = dict(tsv)
            new_tsv["x"] = cxn + xr
            new_tsv["y"] = cyn + yr
            chiplet["tsvs"][tid] = new_tsv
    # Return a rotated copy of the chiplet
    return chiplet

# Construct a graph representation of the ICI network
def construct_adj_list(chiplets, placement, links):
    n_chiplets = len(placement["chiplets"])
    adj_list = [[] for _ in range(n_chiplets)]
    # Inspect the links to specify the adj_list
    for link in links:
        pairs = [(link["src"], link["dst"]), (link["dst"], link["src"])] if link["bidirectional"] else [(link["src"], link["dst"])]
        for (src, dst) in pairs:
            if dst not in adj_list[src]:
                adj_list[src].append(dst)
    # Sort the adjacency lists
    for src in range(len(adj_list)):
        adj_list[src].sort()
    # Return the constructed adjacency list
    return adj_list

def convert_by_unit_traffic_to_by_chiplet_traffic(traffic_by_unit):
    traffic_by_chiplet = {}
    for ((src_cid, src_uid),(dst_cid, dst_uid)) in traffic_by_unit.keys():
        new_key = (src_cid, dst_cid)
        if new_key not in traffic_by_chiplet:
            traffic_by_chiplet[new_key] = 0
        traffic_by_chiplet[new_key] += traffic_by_unit[((src_cid, src_uid),(dst_cid, dst_uid))]
    return traffic_by_chiplet

def print(txt):
    builtins.print(txt if get_print_prefix() == "" else ("[" + get_print_prefix() + "] " + txt))

