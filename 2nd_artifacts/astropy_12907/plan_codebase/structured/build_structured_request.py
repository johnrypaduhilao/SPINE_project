"""Build the structured request for one SWE-bench instance.

Fills the two intent slots in request_structured_v2_template.txt and proves
nothing else changed. The template opens with the same generic prefix as
run_plan_unstructured.py and run_plan_trajectory.py; this script verifies
that byte identity and aborts if the template drifts.

Run (PowerShell):
  python build_structured_request.py request_structured_v2_template.txt <instance.json>

Output: outputs\\request_structured_<instance_id>.txt plus the proof report.
"""

import difflib
import hashlib
import json
import os
import sys

INTENT_TOKEN = "{{INTENT}}"
INTENT_JSON_TOKEN = "{{INTENT_JSON}}"

EXPECTED_PREFIX = (
    "You are a software engineering agent working in a repository. "
    "The repository has the following reported issue.\n"
    "\n"
    "<problem_statement>\n"
    + INTENT_TOKEN + "\n"
    "</problem_statement>\n"
    "\n"
    "Do not make any changes to the repository in this session. "
    "Show me your plan for resolving this issue: the steps you would "
    "take and your reasoning.\n"
)


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: python build_structured_request.py <template.txt> <instance.json>")
    tpl_path, inst_path = sys.argv[1], sys.argv[2]
    text = open(tpl_path, encoding="utf-8").read()
    inst = json.load(open(inst_path, encoding="utf-8"))
    ps = inst["problem_statement"].replace("\r\n", "\n")

    if not text.startswith(EXPECTED_PREFIX):
        sys.exit("ABORT: template prefix differs from the shared plan-runner "
                 "prefix; the three-cell identity proof would not hold")
    checks = [
        ("prefix intent token", INTENT_TOKEN, 1),
        ("schema intent token", INTENT_JSON_TOKEN, 1),
    ]
    for name, needle, expected in checks:
        n = text.count(needle)
        if n != expected:
            sys.exit("ABORT: %s found %d times, expected %d" % (name, n, expected))

    out = text.replace(INTENT_TOKEN, ps, 1)
    out = out.replace(INTENT_JSON_TOKEN, json.dumps(ps), 1)
    assert INTENT_TOKEN not in out and INTENT_JSON_TOKEN not in out

    os.makedirs("outputs", exist_ok=True)
    out_path = os.path.join("outputs",
                            "request_structured_%s.txt" % inst["instance_id"])
    open(out_path, "w", encoding="utf-8", newline="\n").write(out)

    diff = list(difflib.unified_diff(text.splitlines(), out.splitlines(),
                                     lineterm="", n=0))
    hunks = sum(1 for l in diff if l.startswith("@@"))
    subs = [
        ("1 prefix intent", ps in out),
        ("2 schema intent", ('"intent": %s' % json.dumps(ps)) in out),
    ]
    nonascii = sum(1 for c in out if ord(c) > 127)
    print("wrote %s" % out_path)
    for name, v in subs:
        print("  substitution %-18s %s" % (name, "OK" if v else "MISSING"))
    print("prefix sha256   : %s" % sha256_text(EXPECTED_PREFIX))
    print("template sha256 : %s" % sha256_text(text))
    print("request sha256  : %s" % sha256_text(out))
    print("diff hunks      : %d (2 is normal: one per intent slot)" % hunks)
    print("non-ascii chars : %d %s" % (nonascii, "(inspect!)" if nonascii else ""))
    if not all(v for _n, v in subs):
        sys.exit("ABORT: a substitution is missing; do not use the output")


if __name__ == "__main__":
    main()
