"""Replay only an observed injection schedule to validate the live interface.

This validation never drives target execution. It runs after completion and
compares the unchanged standalone native binary to the persistent adapter.
"""
from pathlib import Path
import shutil

from wafer_sim.adapters import booksim
from wafer_sim.io import read_json,write_json


def compare_reference(inputs, online_directory, directory, binary, messages, seed):
    directory = Path(directory)
    directory.mkdir(exist_ok=False)
    relative = Path("rapidchiplet/booksim2/src")
    for part in ("rc_configs","rc_topologies","rc_stats","rc_xy_info"):
        (directory/relative/part).mkdir(parents=True)
    shutil.copyfile(Path(online_directory)/relative/"rc_topologies/network.anynet",
                    directory/relative/"rc_topologies/network.anynet")
    trace = [dict(id=m["id"],cycle=m["ready"],src=m["source"],dst=m["destination"],
                  num_deps=0,rev_deps=[],num_flits=m["expected_flits"],duration=0,
                  ignore=False,cpu_resource=-1) for m in sorted(messages,key=lambda m:m["id"])]
    write_json(directory/"validation_trace.json",trace)
    config = booksim.prepare_config(inputs,directory,directory/"validation_trace.json",seed,60,False)
    execution = booksim.run(binary,config,directory,60)
    report = read_json(directory/"trace_report.json")
    fields = {"ready_cycle":"ready","generated_cycle":"generated",
              "first_inject_cycle":"first_inject","last_inject_cycle":"last_inject",
              "first_eject_cycle":"first_eject","finish_cycle":"last_eject"}
    observed = {m["id"]:m for m in messages}
    if (report["instructions_completed"] != len(messages) or
            report["flits_ejected"] != sum(m["expected_flits"] for m in messages)):
        raise ValueError("Standalone/native message or flit conservation mismatch")
    for event in report["events"]:
        message = observed[event["id"]]
        if not event["completed"] or event["flits_remaining"] != 0:
            raise ValueError("Standalone/native completion mismatch")
        for field, key in fields.items():
            if event[field] != message[key]:
                raise ValueError(f"Standalone/native timing mismatch: message {event['id']} {key}")
    result = dict(passed=True,messages=len(messages),compared_fields=fields,
                  standalone_binary_sha256=execution["binary_sha256"],
                  role="post-execution network-interface validation, not application replay")
    write_json(directory/"CHECKED.json",result)
    return result
