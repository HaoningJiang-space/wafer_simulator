"""Observe author GOAL writes and model calls, without editing author sources.

This records reconstruction provenance, not a correspondence to published
operations. That correspondence must be independently established afterwards.
"""
import ast
import builtins
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
import re
import sys

import numpy as np

from wafer_sim.io import digest, write_json

CATEGORIES = {0: "unknown", 1: "measured_interval", 2: "reduction_model",
              3: "copy_model", 4: "reduction_copy_model", 5: "intra_host_transfer_model",
              6: "synchronization_placeholder"}
FIELDS = ("rank", "label", "duration", "cpu", "source_line", "category", "gpu",
          "stream", "group", "event", "peer_gpu", "role", "model_bytes",
          "interval_start", "interval_end", "model_key")
DTYPE = np.dtype([(name, "<i8") for name in FIELDS])
CALC = re.compile(r"l(\d+): calc (-?\d+) cpu (\d+)\n")


def write_sites(source):
    """Find executed source expressions and their enclosing peer branch."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    result = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "file"
                and node.func.attr == "write" and node.args):
            continue
        text = ast.get_source_segment(source, node.args[0])
        if ": calc " not in text:
            continue
        category = 1 if ("ts_group_gpu_start" in text or "{gap}" in text) else (
            6 if ": calc 0 cpu " in text else 0)
        ancestor, peer = node, None
        while ancestor in parents:
            ancestor = parents[ancestor]
            if isinstance(ancestor, ast.If):
                names = sorted({n.id for n in ast.walk(ancestor.test) if isinstance(n, ast.Name)
                                and n.id.startswith("goal_rank_")})
                if len(names) == 1:
                    peer = "gpuId_" + names[0][len("goal_rank_"):]
                    break
        result[node.lineno] = dict(category=category, peer_variable=peer, expression=text)
    return result


class Observer:
    def __init__(self, module, groups, output):
        self.module, self.output = module, Path(output)
        self.source = Path(module.__file__).resolve()
        self.sites = write_sites(self.source.read_text())
        self.group_ids = {id(group): index for hosts in groups.values() for streams in hosts.values()
                          for sequence in streams.values() for index, group in enumerate(sequence)}
        self.event_ids = {id(event): index for hosts in groups.values() for streams in hosts.values()
                          for sequence in streams.values() for group in sequence
                          for index, event in enumerate(group["events"])}
        self.pending, self.rows, self.counts = [], [], Counter()
        self.model_ids, self.models = {}, []
        self.stream = (self.output / "calc_provenance.bin").open("wb")

    def wrap_model(self, name, original):
        def observed(*args, **kwargs):
            value = original(*args, **kwargs)
            self.pending.append((name, args, kwargs, int(value)))
            return value
        return observed

    def record(self, text, frame):
        match = CALC.fullmatch(text)
        if not match:
            if self.pending:
                raise ValueError("A model evaluation was not consumed by its calc write")
            return
        values, line = frame.f_locals, frame.f_lineno
        if Path(frame.f_code.co_filename).resolve() != self.source or line not in self.sites:
            raise ValueError("Unrecognized author calc write site")
        label, duration, cpu = map(int, match.groups())
        site = self.sites[line]
        category = site["category"]
        names = {x[0] for x in self.pending}
        if names:
            category = {frozenset({"get_reduction_time"}): 2,
                        frozenset({"get_copy_time"}): 3,
                        frozenset({"get_reduction_time", "get_copy_time"}): 4,
                        frozenset({"get_intra_node_gpu_transfer_time"}): 5}[frozenset(names)]
            if sum(x[3] for x in self.pending) != duration:
                raise ValueError("Model values do not explain emitted calc duration")
        key, nbytes, role, peer = -1, -1, 0, -1
        if self.pending:
            signature = tuple((name, tuple(args), tuple(sorted(kwargs.items())), value)
                              for name, args, kwargs, value in self.pending)
            if signature not in self.model_ids:
                self.model_ids[signature] = len(self.models)
                self.models.append([dict(function=n, arguments=a, keyword_arguments=k, duration=v)
                                    for n, a, k, v in self.pending])
            key = self.model_ids[signature]
            nbytes = int(self.pending[0][1][0])
        if category == 5:
            role = {"Send": 1, "Recv": 2}[self.pending[0][1][1]]
            variable = site["peer_variable"]
            if variable not in values:
                raise ValueError(f"Cannot identify transfer peer at source line {line}")
            peer = int(values[variable])
        start = end = -1
        group = values.get("group_event")
        if category == 1:
            start = int(values["last_group_event_end_time"])
            end = int(group["ts_group_gpu_start"])
            if max(0, end - start) != duration:
                raise ValueError("Raw interval does not explain emitted duration")
        self.rows.append((int(values["goal_rank"]), label, duration, cpu, line, category,
            int(values.get("gpuId", -1)), int(values.get("streamId", -1)),
            self.group_ids.get(id(group), -1),
            -1 if category == 1 else self.event_ids.get(id(values.get("event")), -1),
            peer, role, nbytes, start, end, key))
        self.counts[CATEGORIES[category]] += 1
        self.pending.clear()
        if len(self.rows) >= 8192:
            self.flush()

    def flush(self):
        self.stream.write(np.asarray(self.rows, dtype=DTYPE).tobytes())
        self.rows.clear()

    def finish(self, success):
        self.flush()
        self.stream.close()
        write_json(self.output / "CALC_PROVENANCE.json", dict(complete=success,
            scope="Reconstructed source writes only; not yet associated with published operations",
            fields=FIELDS, dtype="little-endian signed int64 for every field", categories=CATEGORIES,
            counts=dict(self.counts), source_sha256=digest(self.source),
            binary_sha256=digest(self.output / "calc_provenance.bin"),
            write_sites=self.sites, model_evaluations=self.models))


@contextmanager
def observe_generator(module, groups, output):
    observer = Observer(module, groups, output)
    originals = {name: getattr(module, name) for name in (
        "get_reduction_time", "get_copy_time", "get_intra_node_gpu_transfer_time")}
    if hasattr(module, "open"):
        raise ValueError("Author module already overrides open")

    class Writer:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def write(self, text):
            observer.record(text, sys._getframe(1))
            return self.stream.write(text)

    def observed_open(*args, **kwargs):
        return Writer(builtins.open(*args, **kwargs))

    success = False
    try:
        module.open = observed_open
        for name, original in originals.items():
            setattr(module, name, observer.wrap_model(name, original))
        yield observer
        success = True
    finally:
        del module.open
        for name, original in originals.items():
            setattr(module, name, original)
        observer.finish(success)
