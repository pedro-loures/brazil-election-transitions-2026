"""Restore checked-in analysis inputs/results to their working paths."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def restore():
    records=json.loads((ROOT/"datasets/manifest.json").read_text())["files"]
    for record in records:
        source=(ROOT/record["path"]).resolve();destination=(ROOT/record["restore_path"]).resolve()
        if not source.is_relative_to(ROOT) or not destination.is_relative_to(ROOT):
            raise ValueError("Snapshot paths must stay within the checkout")
        if hashlib.sha256(source.read_bytes()).hexdigest()!=record["sha256"]:
            raise ValueError(f'Snapshot checksum mismatch: {record["path"]}')
    for record in records:
        source=ROOT/record["path"];destination=ROOT/record["restore_path"]
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
    shutil.copytree(ROOT/"docs",ROOT/"results/2026/flowcharts",dirs_exist_ok=True)
    print(f"Restored {len(records)} verified snapshot files and the flow explorer.")


if __name__=='__main__':restore()
