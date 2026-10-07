"""Apply the conversion patch in isolation and test the actual author converter."""
import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from wafer_sim.io import digest, write_json

ROOT = Path("/home/wangziheng/wafer_simulator")


def main():
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Converter validation stays on eex005")
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.output.is_absolute():
        raise ValueError("Fresh absolute output required")
    repo = Path(__file__).resolve().parents[1]
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"]):
        raise ValueError("Clean committed source required")
    upstream = repo / "third_party/chakra"
    hashes = {str(p.relative_to(upstream)): digest(p) for p in sorted(upstream.rglob("*")) if p.is_file()}
    args.output.mkdir(parents=True, exist_ok=False)
    checkout = args.output / "chakra"
    shutil.copytree(upstream, checkout)
    patch = repo / "patches/chakra-preserve-layout.patch"
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=checkout, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=checkout, check=True)
    schema = ROOT / "deps/chakra-schema/generated/et_def_pb2.py"
    shutil.copy2(schema, checkout / "schema/protobuf/et_def_pb2.py")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (args.output, repo/"src", repo/"tests"))),
               PYTHONDONTWRITEBYTECODE="1")
    log = args.output / "tests.log"
    with log.open("w") as stream:
        subprocess.run([sys.executable, "-m", "unittest", "chakra_converter_patch_case", "-v"],
                       cwd=repo, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
    if any(digest(upstream/name) != sha for name, sha in hashes.items()):
        raise ValueError("Pinned author source changed")
    write_json(args.output / "VALIDATED.json", dict(passed=True, source_commit=commit,
        host=platform.node(), python=sys.version, executable=sys.executable,
        executable_sha256=digest(Path(sys.executable).resolve()), upstream_files_sha256=hashes,
        patch_sha256=digest(patch), generated_schema_sha256=digest(schema),
        tests_log_sha256=digest(log), tests=4, patched_converter_sha256=digest(checkout/"src/converter/pytorch_converter.py"),
        packages=subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True).splitlines(),
        original_capture_modified=False, original_capture_layout_recovered=False, new_simulations_launched=0))
    print(log.read_text(), flush=True)


if __name__ == "__main__":
    main()
