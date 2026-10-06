"""Read the COMPLETE external GOAL capture on the remote host; never truncate.

This first pass reports syntax, operation work, resource IDs, and communication
matching without assigning GPU meaning to CPU stream numbers.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    counts = Counter()
    cpus = defaultdict(set)
    nics = defaultdict(set)
    messages = defaultdict(lambda: [[], []])
    compute_ns = 0
    byte_count = 0
    flits = 0
    rank = None
    declared_ranks = None
    sha = hashlib.sha256()
    operation = re.compile(r"l(\d+): (calc|send|recv) (\d+)(b?)(.*)")
    for line_number, raw in enumerate(args.input.open("rb"), 1):
        sha.update(raw)
        line = raw.decode().strip()
        if not line or line == "}":
            continue
        if line.startswith("num_ranks "):
            declared_ranks = int(line.split()[1])
            continue
        if line.startswith("rank "):
            rank = int(line.split()[1])
            counts["rank_sections"] += 1
            continue
        if " requires " in line or " irequires " in line:
            counts["irequires" if " irequires " in line else "requires"] += 1
            continue
        match = operation.fullmatch(line)
        if not match:
            raise ValueError(f"Unsupported GOAL syntax at line {line_number}: {line[:100]}")
        label, kind, amount, suffix, extra = match.groups()
        amount = int(amount)
        fields = extra.split()
        cpu = int(fields[fields.index("cpu")+1]) if "cpu" in fields else 0
        cpus[rank].add(cpu)
        counts[kind] += 1
        if kind == "calc":
            compute_ns += amount
            continue
        other = int(fields[1])
        tag = int(fields[fields.index("tag")+1])
        nic = int(fields[fields.index("nic")+1]) if "nic" in fields else 0
        nics[rank].add(nic)
        key = (rank, other, tag) if kind == "send" else (other, rank, tag)
        messages[key][kind == "recv"].append((amount, nic, int(label), cpu))
        if kind == "send":
            byte_count += amount
            flits += (amount+1999)//2000
    unmatched, ambiguous, size_mismatch = [], [], []
    endpoint_pairs = Counter()
    for key, (sends, recvs) in messages.items():
        if len(sends) != len(recvs):
            unmatched.append((key, len(sends), len(recvs)))
        elif len(sends) != 1:
            ambiguous.append((key, len(sends)))
        elif sends[0][0] != recvs[0][0]:
            size_mismatch.append(key)
        else:
            endpoint_pairs[(key[0], sends[0][1], key[1], recvs[0][1])] += 1
    result = dict(source=str(args.input), source_sha256=sha.hexdigest(), bytes=args.input.stat().st_size,
                  lines=line_number, declared_ranks=declared_ranks, counts=dict(counts),
                  cpu_ids={str(k): sorted(v) for k,v in cpus.items()},
                  nic_ids={str(k): sorted(v) for k,v in nics.items()},
                  compute_duration_sum_ns=compute_ns, sent_payload_bytes=byte_count,
                  network_flits_at_2000_bytes=flits, distinct_message_keys=len(messages),
                  unmatched_keys=len(unmatched), ambiguous_keys=len(ambiguous), size_mismatch_keys=len(size_mismatch),
                  unmatched_examples=unmatched[:10], ambiguous_examples=ambiguous[:10],
                  size_mismatch_examples=size_mismatch[:10],
                  endpoint_message_counts={str(k):v for k,v in endpoint_pairs.items()},
                  truncated=False, removed_dependencies=0, execution_claim=False)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in {"cpu_ids", "endpoint_message_counts"}},indent=2))


if __name__ == "__main__":
    main()
