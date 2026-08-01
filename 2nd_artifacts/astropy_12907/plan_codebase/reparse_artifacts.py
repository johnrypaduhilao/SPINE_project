"""Recompute the mechanical parse and audit fields of existing plan artifacts.

The run-1-inherited fence stripper split on the first triple-backtick, which
misparses any response whose JSON strings contain code fences. This tool
re-parses with the corrected stripper and rewrites ONLY the mechanical
fields (parsed_steps / parsed_tree, parse_error, structure_audit /
structural_checks). response_text and every other field stay byte-identical.
A mechanical_fields_recomputed flag is added. Manual scoring governs.

Run (PowerShell):
  python reparse_artifacts.py outputs\\plan_trajectory_*.json outputs\\plan_structured_*.json
"""

import glob
import json
import re
import sys

TOOLS = ["search_repo", "open_file", "edit_file", "done"]


def lenient_strip(text):
    body = text.strip()
    m = re.search(r"```(?:json)?\s*\n", body)
    if m and body.rfind("```") > m.end():
        body = body[m.end(): body.rfind("```")]
    return body.strip()


def parse_json(text, want):
    try:
        obj = json.loads(lenient_strip(text))
        if not isinstance(obj, want):
            return None, "top level is not a JSON %s" % want.__name__
        return obj, None
    except Exception as e:
        return None, str(e)


def audit_steps(steps):
    if steps is None:
        return {}
    names = [s.get("action", {}).get("name") for s in steps
             if isinstance(s, dict)]
    return {
        "steps": len(steps),
        "with_thought": sum(1 for s in steps
                            if isinstance(s, dict) and s.get("thought")),
        "with_expected_observation": sum(
            1 for s in steps
            if isinstance(s, dict) and s.get("expected_observation")),
        "action_names": {n: names.count(n) for n in set(names) if n},
        "off_vocabulary_actions": sorted({n for n in names
                                          if n and n not in TOOLS}),
        "has_parent_field": any(isinstance(s, dict) and
                                any("parent" in k.lower() for k in s)
                                for s in steps),
        "has_definer_field": any(isinstance(s, dict) and
                                 any("definer" in k.lower() for k in s)
                                 for s in steps),
    }


def check_tree(tree):
    if tree is None:
        return {}
    pols = tree.get("policies", [])
    if not pols:
        return {"policies": 0}
    by_id = {p.get("id"): p for p in pols if isinstance(p, dict)}
    problems = []
    roots = [p for p in pols if p.get("parent_id") is None]
    if len(roots) != 1:
        problems.append("expected exactly 1 root, found %d" % len(roots))

    def reaches_root(p):
        seen = set()
        while p.get("parent_id") is not None:
            pid = p["parent_id"]
            if pid in seen or pid not in by_id:
                return False
            seen.add(pid)
            p = by_id[pid]
        return True

    n = len(pols)
    tc = sum(reaches_root(p) for p in pols) / n
    ac = sum(1 for p in pols if p.get("definer")) / n
    ef = sum(1 for p in pols if p.get("rationale")) / n
    for p in pols:
        lvl, d = p.get("level"), p.get("definer")
        if p.get("parent_id") is None and d != "human operator":
            problems.append("%s: root definer is %r" % (p.get("id"), d))
        if p.get("parent_id") is not None and d != "assurance engine":
            problems.append("%s: refined definer is %r" % (p.get("id"), d))
        if lvl not in ("declarative", "definitive", "imperative"):
            problems.append("%s: unknown level %r" % (p.get("id"), lvl))
    levels = {}
    for p in pols:
        levels[p.get("level")] = levels.get(p.get("level"), 0) + 1
    return {"policies": n, "tc_mechanical": round(tc, 2),
            "ac_mechanical": round(ac, 2), "ef_mechanical": round(ef, 2),
            "levels": levels, "problems": problems}


def main():
    paths = []
    for arg in sys.argv[1:]:
        paths.extend(glob.glob(arg))
    if not paths:
        sys.exit("usage: python reparse_artifacts.py <artifact.json> ...")
    for p in sorted(set(paths)):
        d = json.load(open(p, encoding="utf-8"))
        cell = d.get("cell")
        if cell == "plan_trajectory":
            steps, err = parse_json(d["response_text"], list)
            d["parsed_steps"] = steps
            d["parse_error"] = err
            d["structure_audit"] = audit_steps(steps)
            summary = d["structure_audit"] or err
        elif cell == "plan_structured":
            tree, err = parse_json(d["response_text"], dict)
            d["parsed_tree"] = tree
            d["parse_error"] = err
            d["structural_checks"] = check_tree(tree)
            summary = d["structural_checks"] or err
        else:
            print("skip (no mechanical parse fields): %s" % p)
            continue
        d["mechanical_fields_recomputed"] = True
        json.dump(d, open(p, "w", encoding="utf-8"), indent=2,
                  ensure_ascii=False)
        print("reparsed %s\n  -> %s" % (p, json.dumps(summary)))


if __name__ == "__main__":
    main()
