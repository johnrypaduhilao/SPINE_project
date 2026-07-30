"""
Audit-cost micro-benchmark for SPINE.

Measures the processing time of the audit operation that recovers one
intent-to-action path:
  SPINE   : walk parent pointers from an enforced (leaf) policy to the root.
            Cost is O(depth); it touches only the policies on the path and
            never the execution log, so it is constant in the size of the log.
  Baseline: any post-hoc reconstruction from a flat event log must at minimum
            scan all n records. Cost is O(n) and grows as logging accumulates
            (and still cannot reassemble the structured lineage; see the
            recoverability results).

Reports a per-operation time for the SPINE traversal on the three ground-truth
trees, and the O(n) scan time at several log sizes for contrast.
Run on Windows: `python overhead_traversal_bench.py` (PowerShell) or
`py overhead_traversal_bench.py` (Git Bash).
"""
import timeit

# id -> parent_id for each ground-truth tree (structure only; that is all the
# audit traversal needs).
CODE = {  # protect_files, 16 policies, max depth 3
    "P0": None, "P1": "P0", "P1.1": "P1", "P2": "P0", "P2.1": "P2",
    "P3": "P0", "P3.1": "P3", "P3.2": "P3", "P3.3": "P3",
    "P4": "P0", "P4.1": "P4", "P4.2": "P4", "P5": "P0", "P5.1": "P5",
    "P6": "P0", "P6.1": "P6",
}
AV = {  # decelerate / Law46, 9 policies
    "P0": None, "P1": "P0", "P2": "P0", "P3": "P0",
    "P1.1": "P1", "P2.1": "P2", "P3.1": "P3", "P3.2": "P3", "P3.3": "P3",
}
EMB = {  # wipe stovetop, 11 policies
    "P0": None, "P1": "P0", "P2": "P0", "P2.1": "P2", "P3": "P0",
    "P4": "P0", "P4.1": "P4", "P4.2": "P4", "P4.3": "P4", "P5": "P0", "P6": "P0",
}

def depth(tree, pid):
    d = 0
    while tree[pid] is not None:
        pid = tree[pid]; d += 1
    return d

def traverse(tree, leaf):
    """The audit operation: collect the root-to-leaf path by parent pointers."""
    path, cur = [], leaf
    while cur is not None:
        path.append(cur)
        cur = tree[cur]
    path.reverse()
    return path

def deepest_leaf(tree):
    leaves = [p for p in tree if p not in set(tree[c] for c in tree if tree[c])]
    return max(leaves, key=lambda p: depth(tree, p))

REPS = 1_000_000
print("SPINE audit traversal (parent-pointer walk, leaf -> root)")
print(f"{'tree':<10}{'policies':>9}{'depth':>7}{'per-op (us)':>14}")
for name, tree in [("code", CODE), ("AV", AV), ("embodied", EMB)]:
    leaf = deepest_leaf(tree)
    d = depth(tree, leaf)
    t = timeit.timeit(lambda: traverse(tree, leaf), number=REPS) / REPS
    print(f"{name:<10}{len(tree):>9}{d:>7}{t*1e6:>14.3f}")

print("\nBaseline O(n) scan over a flat execution log (minimum work to attempt")
print("reconstruction; touches every record):")
print(f"{'log size n':>12}{'scan (us)':>12}")
for n in (100, 1_000, 10_000, 100_000):
    log = [{"i": i, "evt": "tool_call"} for i in range(n)]
    reps = max(10, 2_000_000 // n)
    t = timeit.timeit(lambda: sum(1 for _ in log), number=reps) / reps
    print(f"{n:>12}{t*1e6:>12.2f}")
