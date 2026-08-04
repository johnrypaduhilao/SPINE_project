"""Re-derives the run-2 Overhead sheet inputs. Manual numbers govern; this reproduces them.

Trees: pointer traversal from the deepest leaf to P0, O(depth), timed in microseconds,
plus the sheet's stated bytes convention (len of json.dumps(parsed_tree, indent=2)).
Prose and trajectory artifacts: full-text scan as the O(n) reconstruction baseline.

Run from astropy_12907 (PowerShell):
  python review_tools\\measure_overhead.py
"""

import glob
import json
import os
import sys
import timeit

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."

PATTERNS = [
    ("CLAUDE tree", "CLAUDE_SONNET/structured/outputs/plan_structured_*.json"),
    ("GPT tree", "OPENAI/structured/outputs/plan_structured_*.json"),
    ("CLAUDE prose", "CLAUDE_SONNET/unstructured/outputs/plan_unstructured_*.json"),
    ("GPT prose", "OPENAI/unstructured/outputs/plan_unstructured_*.json"),
    ("CLAUDE traj", "CLAUDE_SONNET/trajectory/outputs/plan_trajectory_*.json"),
    ("GPT traj", "OPENAI/trajectory/outputs/plan_trajectory_*.json"),
]


def main():
    for label, pat in PATTERNS:
        hits = [p for p in glob.glob(os.path.join(ROOT, pat)) if "ARCHIVED" not in p]
        if len(hits) != 1:
            print("%-13s MISSING or ambiguous: %s" % (label, pat))
            continue
        d = json.load(open(hits[0], encoding="utf-8"))
        if "tree" in label:
            tree = d["parsed_tree"]
            pol = {x["id"]: x for x in tree["policies"]}
            parent = {x["id"]: x.get("parent_id") for x in tree["policies"]}

            def depth(i):
                n = 0
                while parent[i]:
                    i = parent[i]
                    n += 1
                return n

            leaf = max(pol, key=depth)

            def traverse():
                chain, i = [], leaf
                while i is not None:
                    chain.append(pol[i])
                    i = parent[i]
                return chain

            t = min(timeit.repeat(traverse, number=10000, repeat=7)) / 10000 * 1e6
            conv_bytes = len(json.dumps(tree, indent=2).encode("utf-8"))
            print("%-13s nodes=%2d chain=%d leaf=%-5s traversal=%.2f us  "
                  "bytes(convention)=%d  file=%d B"
                  % (label, len(pol), depth(leaf) + 1, leaf, t, conv_bytes,
                     os.path.getsize(hits[0])))
        else:
            text = d["response_text"]

            def scan():
                return [l for l in text.splitlines()
                        if "_cstack" in l or "separab" in l or "P4" in l]

            t = min(timeit.repeat(scan, number=2000, repeat=7)) / 2000 * 1e6
            print("%-13s chars=%6d full-scan=%.2f us  file=%d B"
                  % (label, len(text), t, os.path.getsize(hits[0])))


if __name__ == "__main__":
    main()
