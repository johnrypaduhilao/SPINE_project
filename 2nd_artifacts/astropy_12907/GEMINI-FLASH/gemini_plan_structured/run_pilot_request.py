"""
run_pilot_request.py

Send the built pilot request to the model (one call, temperature 0) and
save the returned policy tree. Then run structural checks: JSON validity,
parent pointers resolve, definers by level, rationale presence, TC/AC/EF.

Run (PowerShell):
  $env:GOOGLE_API_KEY="..."
  python run_pilot_request.py outputs\\request_pilot_astropy__astropy-12907.txt

Dry run (no API key, no call; just validates the request file):
  python run_pilot_request.py outputs\\request_pilot_astropy__astropy-12907.txt --dry-run

One call costs a modest amount; do not loop it. Manual scoring governs;
the checks here are the reproducibility layer only.
"""

import json
import os
import sys

MODEL = "gemini-3.5-flash"


def structural_checks(tree):
    pols = tree.get("policies", [])
    by_id = {p["id"]: p for p in pols}
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

    tc = sum(reaches_root(p) for p in pols) / len(pols) if pols else 0.0
    ac = sum(1 for p in pols if p.get("definer")) / len(pols) if pols else 0.0
    ef = sum(1 for p in pols if p.get("rationale")) / len(pols) if pols else 0.0

    for p in pols:
        lvl, d = p.get("level"), p.get("definer")
        if p.get("parent_id") is None and d != "human operator":
            problems.append("%s: root definer should be human operator" % p["id"])
        if p.get("parent_id") is not None and d != "assurance engine":
            problems.append("%s: refined definer should be assurance engine" % p["id"])
        if lvl not in ("declarative", "definitive", "imperative"):
            problems.append("%s: unknown level %r" % (p["id"], lvl))

    levels = {}
    for p in pols:
        levels[p.get("level")] = levels.get(p.get("level"), 0) + 1
    return tc, ac, ef, levels, problems


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python run_pilot_request.py <request.txt> [--dry-run]")
    req_path = sys.argv[1]
    dry = "--dry-run" in sys.argv
    request = open(req_path, encoding="utf-8").read()
    print("request: %s (%d chars)" % (req_path, len(request)))
    if dry:
        print("dry run: request file reads fine; no call made")
        return

    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0, max_tokens=8000)

    # Stream: whatever arrives is kept. If the token budget runs out (or the
    # stream drops) mid-answer, we still hold everything generated so far
    # instead of losing the whole trajectory to one failed blocking call.
    parts, truncated = [], None
    print("streaming from %s ..." % MODEL)
    try:
        for chunk in llm.stream(request):
            c = chunk.content
            if not isinstance(c, str):
                c = " ".join(b.get("text", "") for b in c if isinstance(b, dict))
            if c:
                parts.append(c)
    except Exception as e:                       # keep the partial trajectory
        truncated = str(e)
    raw = "".join(parts).strip()
    print("received %d chars%s" % (len(raw), " (stream cut short)" if truncated else ""))
    if not raw:
        sys.exit("no text came back%s" % (": " + truncated if truncated else ""))
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        tree = json.loads(raw)
    except json.JSONDecodeError as e:
        os.makedirs("outputs", exist_ok=True)
        open("outputs/pilot_tree_RAW.txt", "w", encoding="utf-8").write(raw)
        sys.exit("output was not valid JSON (%s); raw saved to "
                 "outputs/pilot_tree_RAW.txt for manual reading%s" %
                 (e, " (the stream was cut short, so the text is probably "
                     "just unfinished)" if truncated else ""))

    os.makedirs("outputs", exist_ok=True)
    out = "outputs/pilot_tree_astropy__astropy-12907.json"
    json.dump(tree, open(out, "w", encoding="utf-8"), indent=2)

    tc, ac, ef, levels, problems = structural_checks(tree)
    print("tree -> %s" % out)
    print("policies: %d  levels: %s" % (len(tree.get("policies", [])),
                                        json.dumps(levels)))
    print("TC %.2f  AC %.2f  EF %.2f  (structural; manual scoring governs)"
          % (tc, ac, ef))
    if problems:
        print("structural problems (%d):" % len(problems))
        for p in problems:
            print("  - " + p)
    else:
        print("structural problems: none")
    print("\nWHAT THIS RUN DID (plain terms):")
    print("  Sent one pilot request to %s and streamed the answer back." % MODEL)
    print("  The answer was a policy tree: %d policies, one root goal with the"
          % len(tree.get("policies", [])))
    print("  rest hanging off it as sub-goals. Saved as JSON to %s." % out)
    print("  Then checked the shape only: %.0f%% of policies trace back to the"
          % (tc * 100))
    print("  root (TC), %.0f%% say who set them (AC), %.0f%% give a reason (EF)."
          % (ac * 100, ef * 100))
    print("  %s Nothing here judges whether the content is any good."
          % ("No shape problems found." if not problems
             else "%d shape problem(s) listed above." % len(problems)))
    print("\nREADING CHECKS (by hand, before anything else):")
    print("  1. P0: does it restate the GOAL (fix separability for nested")
    print("     models), treating the code blocks as evidence, not commands?")
    print("  2. Does the tree decompose into diagnose / fix / verify style")
    print("     sub-goals, or does it drift into generic repo hygiene?")
    print("  3. Spot-check three rationales: do they say WHY-from-parent?")


if __name__ == "__main__":
    main()
