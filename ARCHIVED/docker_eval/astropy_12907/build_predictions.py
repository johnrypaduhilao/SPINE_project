"""
build_predictions.py

Builds SWE-bench prediction files from the phase1v2 and dispatch
artifacts. One JSONL per cell so each cell evaluates independently.

Patch modes (--patch-mode):
  source-only  (default) drop per-file diff segments whose path is under
               a tests directory; the resolved metric is defined by the
               held-out tests, and two Claude cells edit the same
               compound_models lines the held-out test patch edits, so
               submitting test edits would fail application for a
               mechanical reason unrelated to fix correctness. Uniform
               across all cells.
  as-is        submit the captured model_patch unmodified.

Every emitted patch is checked for the gold one-line fix string and
hashed; the manifest records mode, kept and dropped files, chars, and
sha256 per cell. Nothing here is a result; Docker decides resolved.

Run (PowerShell, from anywhere):
  python build_predictions.py ^
      --phase1v2-dir "D:\\THESIS REPOSITORY\\SPINE_project\\2nd_artifacts\\execution_agent\\phase1v2" ^
      --dispatch-dir "D:\\THESIS REPOSITORY\\SPINE_project\\2nd_artifacts\\structured_execution_agent\\00" ^
      --out-dir predictions
"""

import argparse
import glob
import hashlib
import json
import os
import sys

GOLD = "cright[-right.shape[0]:, -right.shape[1]:] = right"

CELL_FOLDERS = [
    ("01_NOPLAN", "noplan"),
    ("02_UNSTRUCTURED", "unstructured"),
    ("00_TRAJECTORY", "trajectory"),
    ("03_STRUCTURED", "structured"),
]


def model_tag(model):
    return "C" if "claude" in model.lower() else "G"


def is_test_path(path):
    parts = path.replace("\\", "/").split("/")
    return "tests" in parts or "test" in parts or \
        os.path.basename(path).startswith("test_")


def split_patch(patch):
    segs, cur = [], []
    for line in patch.splitlines(keepends=True):
        if line.startswith("diff --git ") and cur:
            segs.append("".join(cur))
            cur = []
        cur.append(line)
    if cur:
        segs.append("".join(cur))
    return segs


def seg_path(seg):
    first = seg.splitlines()[0]
    return first.split(" b/")[-1].strip()


def filter_patch(patch, mode):
    segs = split_patch(patch)
    kept, dropped = [], []
    for s in segs:
        p = seg_path(s)
        if mode == "source-only" and is_test_path(p):
            dropped.append(p)
        else:
            kept.append(s)
    out = "".join(kept)
    if out and not out.endswith("\n"):
        out += "\n"
    return out, [seg_path(s) for s in kept], dropped


def load_cells(phase1v2_dir, dispatch_dir):
    cells = []
    for folder, label in CELL_FOLDERS:
        pat = os.path.join(phase1v2_dir, folder, "outputs", "*.json")
        for f in sorted(glob.glob(pat)):
            d = json.load(open(f, encoding="utf-8"))
            cells.append((label, f, d))
    if dispatch_dir:
        pat = os.path.join(dispatch_dir, "outputs", "*.json")
        for f in sorted(glob.glob(pat)):
            d = json.load(open(f, encoding="utf-8"))
            cells.append(("dispatch", f, d))
    return cells


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase1v2-dir", required=True)
    ap.add_argument("--dispatch-dir", default=None)
    ap.add_argument("--out-dir", default="predictions")
    ap.add_argument("--patch-mode", choices=["source-only", "as-is"],
                    default="source-only")
    args = ap.parse_args()

    cells = load_cells(args.phase1v2_dir, args.dispatch_dir)
    if not cells:
        sys.exit("no artifacts found; check the directory arguments")

    os.makedirs(args.out_dir, exist_ok=True)
    manifest = {"patch_mode": args.patch_mode, "cells": []}
    rows = []
    for label, f, d in cells:
        tag = model_tag(d["executor_model"])
        cell_id = "%s_%s" % (label, tag)
        run = d.get("run")
        raw = d["model_patch_capture"]["model_patch"]
        patch, kept, dropped = filter_patch(raw, args.patch_mode)
        if not patch.strip():
            sys.exit("cell %s produced an empty patch under mode %s; "
                     "aborting" % (cell_id, args.patch_mode))
        gold = GOLD in patch
        sha = hashlib.sha256(patch.encode("utf-8")).hexdigest()
        pred = {"instance_id": d["instance_id"],
                "model_name_or_path": "spine_%s_run%s" % (cell_id, run),
                "model_patch": patch}
        out = os.path.join(args.out_dir, "pred_%s_run%s.jsonl"
                           % (cell_id, run))
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(pred) + "\n")
        manifest["cells"].append({
            "cell": cell_id, "run": run, "artifact": os.path.basename(f),
            "prediction_file": os.path.basename(out),
            "patch_sha256": sha, "patch_chars": len(patch),
            "files_kept": kept, "files_dropped": dropped,
            "gold_fix_present": gold})
        rows.append((cell_id, run, len(patch), gold,
                     ",".join(dropped) or "-", sha[:12]))

    mpath = os.path.join(args.out_dir, "manifest.json")
    json.dump(manifest, open(mpath, "w", encoding="utf-8"), indent=2)

    print("mode: %s   cells: %d" % (args.patch_mode, len(rows)))
    print("%-16s %-4s %-6s %-5s %-42s %s" % (
        "cell", "run", "chars", "gold", "dropped", "sha12"))
    for r in rows:
        print("%-16s %-4s %-6d %-5s %-42s %s" % r)
    print("manifest: %s" % mpath)


if __name__ == "__main__":
    main()
