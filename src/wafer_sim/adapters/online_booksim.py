"""Persistent BookSim process: live submissions and next-completion boundaries."""
import json
import os
from pathlib import Path
import select
import subprocess
import time

from wafer_sim.io import digest, write_json
from wafer_sim.workloads.spatial import natural


def prepare_online_config(inputs, directory, seed=1):
    from wafer_sim.adapters.booksim import prepare_config
    directory = Path(directory).resolve()
    write_json(directory/"empty_network_input.json", [])
    return prepare_config(inputs, directory, directory/"empty_network_input.json", seed,
                          timeout=60, skip_idle=False)


class OnlineBookSim:
    def __init__(self, binary, config, directory, *, flit_bytes, timeout=60):
        natural(flit_bytes, "flit bytes", positive=True)
        self.flit_bytes, self.timeout = flit_bytes, timeout
        self.now = 0
        self.pending, self.messages = {}, []
        self.buffer = b""
        self.directory = Path(directory)
        self.logs = [(self.directory / name).open("w") for name in
                     ("online_stdout.log", "online_stderr.log", "online_protocol.jsonl")]
        self.read_fd, write_fd = os.pipe()
        try:
            self.process = subprocess.Popen([str(Path(binary).resolve()), str(Path(config).resolve()), str(write_fd)],
                cwd=self.directory, stdin=subprocess.PIPE, stdout=self.logs[0], stderr=self.logs[1],
                pass_fds=(write_fd,), text=True)
        finally:
            os.close(write_fd)
        self.identity = dict(binary_sha256=digest(binary), config_sha256=digest(config),
                             flit_bytes=flit_bytes, clock="submit before cycle t; receive at end boundary c+1")
        try:
            hello = self._receive()
            if not hello.get("ready") or hello["cycle"] != 0:
                raise ValueError("Unexpected native initialization")
            self.nodes = hello["nodes"]
        except BaseException:
            self.abort()
            raise

    def _receive(self):
        deadline = time.monotonic()+self.timeout
        while b"\n" not in self.buffer:
            remaining = deadline-time.monotonic()
            if remaining <= 0 or not select.select([self.read_fd], [], [], remaining)[0]:
                raise TimeoutError("Online BookSim response timeout")
            chunk = os.read(self.read_fd, 65536)
            if not chunk:
                raise RuntimeError("Online BookSim exited without a response; inspect stderr")
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        reply = json.loads(line)
        self.logs[2].write(json.dumps(dict(reply=reply))+"\n"); self.logs[2].flush()
        if not reply.get("ok"):
            raise RuntimeError(reply.get("error", "Online BookSim failure"))
        return reply

    def _request(self, request):
        self.logs[2].write(json.dumps(dict(request=request))+"\n"); self.logs[2].flush()
        self.process.stdin.write(json.dumps(request)+"\n"); self.process.stdin.flush()
        return self._receive()

    def submit(self, token, transfer, cycle):
        if cycle != self.now or token in self.pending or any(m["token"] == token for m in self.messages):
            raise ValueError("Repeated transfer or mismatched execution/network clock")
        natural(transfer.size_bytes, "transfer bytes", positive=True)
        identity = len(self.messages)+len(self.pending)
        count = (transfer.size_bytes+self.flit_bytes-1)//self.flit_bytes
        reply = self._request(dict(command="submit", id=identity, cycle=cycle,
            source=transfer.source_endpoint, destination=transfer.destination_endpoint, flits=count))
        if reply["id"] != identity or reply["cycle"] != cycle:
            raise ValueError("Native submission acknowledgement mismatch")
        self.pending[token] = dict(id=identity, token=token, ready=cycle,
            bytes=transfer.size_bytes, flit_bytes=self.flit_bytes, expected_flits=count,
            source=transfer.source_endpoint, destination=transfer.destination_endpoint,
            data=transfer.data, source_memory=transfer.source_memory,
            destination_memory=transfer.destination_memory)

    def advance(self, until):
        natural(until, "network boundary")
        reply = self._request(dict(command="advance", until=until))
        if not self.now <= reply["cycle"] <= until:
            raise ValueError("Native clock moved outside the conservative boundary")
        self.now = reply["cycle"]
        completed = []
        for event in reply["completed"]:
            matches = [token for token, row in self.pending.items() if row["id"] == event["id"]]
            if len(matches) != 1:
                raise ValueError("Unknown or repeated native completion")
            token = matches[0]
            row = self.pending.pop(token)
            if any(event[k] != row[k] for k in ("id", "source", "destination", "ready")):
                raise ValueError("Native completion identity mismatch")
            if event["finish"] != self.now or len(event["flits"]) != row["expected_flits"]:
                raise ValueError("Premature or mistimed all-flit completion")
            row.update(event)
            self.messages.append(row)
            completed.append(token)
        return completed

    def close(self):
        if self.pending:
            raise ValueError("Cannot close an incomplete network")
        final = self._request(dict(command="close"))
        self.process.stdin.close()
        if self.process.wait(timeout=self.timeout) != 0 or not final["drained"]:
            raise RuntimeError("Native network did not close cleanly")
        self._close_files()
        record = dict(identity=self.identity, messages=sorted(self.messages,key=lambda m:m["id"]),
                      final=final, complete=True)
        write_json(self.directory/"online_network.json", record)
        return record

    def _close_files(self):
        if self.read_fd is not None:
            os.close(self.read_fd); self.read_fd = None
        for stream in self.logs:
            if not stream.closed: stream.close()

    def abort(self):
        if hasattr(self, "process"):
            if self.process.poll() is None:
                self.process.kill(); self.process.wait()
            if self.process.stdin and not self.process.stdin.closed: self.process.stdin.close()
        self._close_files()
