"""Native BookSim invocation. Always retain logs; incomplete runs are failures."""
from pathlib import Path
import re
import subprocess
import time

from wafer_sim.adapters.wow import working_directory
from wafer_sim.io import digest, read_json, write_json


def prepare_config(inputs, directory, trace_path, seed, timeout=120, skip_idle=True):
    from rapidchiplet import booksim_wrapper
    directory = Path(directory).resolve()
    config = inputs["booksim_config"].copy()
    config.pop("repetitions", None)  # author Python orchestration metadata
    config.update(seed=seed, trace_file=str(Path(trace_path).resolve()),
                  trace_report=str(directory / "trace_report.json"),
                  trace_skip_idle=int(skip_idle), mode="trace", ignore_cycles=0,
                  warmup_periods=0, sim_count=1, sample_period=1000000000,
                  trace_time_out=timeout, time_limit=timeout)
    modified = dict(inputs, booksim_config=config)
    with working_directory(directory):
        booksim_wrapper.export_booksim_config(modified, "network", 1.0)
    return directory / "rapidchiplet/booksim2/src/rc_configs/network.conf"


def run(binary, config, directory, timeout=120, require_report=True):
    directory = Path(directory).resolve()
    start = time.monotonic()
    timed_out = False
    with (directory / "stdout.log").open("w") as stdout, (directory / "stderr.log").open("w") as stderr:
        try:
            result = subprocess.run([str(Path(binary).resolve()), str(Path(config).resolve())],
                                    cwd=directory, stdout=stdout, stderr=stderr, timeout=timeout+10)
            return_code = result.returncode
        except subprocess.TimeoutExpired:
            return_code = -1
            timed_out = True
    record = dict(return_code=return_code, wall_seconds=time.monotonic()-start,
                  timed_out=timed_out, binary_sha256=digest(binary), config_sha256=digest(config))
    log = (directory / "stdout.log").read_text()
    metrics = {}
    for label in ("Packet latency average", "Network latency average", "Hops average",
                  "Total cycles until trace completion", "Total number of trace messages simulated"):
        number = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
        # Upstream prints -nan when there are no packets. Such a network metric
        # is undefined, while the compute-only completion report remains valid.
        matches = re.findall(re.escape(label) + r"\s*=\s*(" + number + r")(?:\s|$)", log)
        if matches:
            metrics[label] = float(matches[-1])
    record["network_metrics"] = metrics
    report_path = directory / "trace_report.json"
    if require_report:
        record["complete"] = report_path.exists() and read_json(report_path).get("complete", False)
    write_json(directory / "execution.json", record)
    if return_code != 0 or (require_report and not record["complete"]):
        raise RuntimeError(f"BookSim did not complete: {directory}; code={return_code}")
    return record
