"""
build_pilot_request.py

Build the pilot's structured request from two authoritative local files:
the vetted request artifact and the SWE-bench instance JSON. Applies
EXACTLY four substitutions (persona clause, domain parenthetical, the
intent in the NOW section, the intent string inside the OUTPUT FORMAT
schema) and then prints a diff report proving nothing else changed.

Run (PowerShell):
  python build_pilot_request.py request_corrected_complex.txt SWE-output\\astropy__astropy-12907.json

Output: outputs\\request_pilot_<instance_id>.txt plus the diff report.
"""

import difflib
import json
import os
import sys

OLD_PERSONA = ("policy-enforcement agent that governs a sensitive-file "
               "workspace")
NEW_PERSONA = ("policy-refinement agent that governs a software-repository "
               "issue-resolution workspace")

OLD_DOMAIN = ("        (domain: code-execution agent governing a "
              "sensitive-file workspace)")
NEW_DOMAIN = ("        (domain: code-execution agent resolving a "
              "repository issue)")


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: python build_pilot_request.py <request.txt> <instance.json>")
    req_path, inst_path = sys.argv[1], sys.argv[2]
    text = open(req_path, encoding="utf-8").read()
    inst = json.load(open(inst_path, encoding="utf-8"))
    ps = inst["problem_statement"].replace("\r\n", "\n").strip()

    # locate the old intent: the quoted string that appears once in the NOW
    # section and once inside the schema. It starts after 'INTENT: "' in the
    # NOW section and ends at the closing quote before the newline+domain.
    now_marker = 'NOW DO THE SAME FOR THIS INTENT:\nINTENT: "'
    i = text.index(now_marker) + len(now_marker)
    j = text.index('"', i)
    old_intent = text[i:j]

    checks = [
        ("persona clause", OLD_PERSONA, 1),
        ("domain parenthetical", OLD_DOMAIN, 1),
        ("intent string", old_intent, 2),
    ]
    for name, needle, expected in checks:
        n = text.count(needle)
        if n != expected:
            sys.exit("ABORT: %s found %d times, expected %d; request file "
                     "does not match the vetted artifact" % (name, n, expected))

    out = text.replace(OLD_PERSONA, NEW_PERSONA, 1)
    out = out.replace(OLD_DOMAIN, NEW_DOMAIN, 1)
    # NOW-section intent: raw, verbatim, inside the existing quotes
    out = out.replace('INTENT: "%s"' % old_intent, 'INTENT: "%s"' % ps, 1)
    # schema intent: JSON-escaped single-line string
    out = out.replace('"intent": "%s"' % old_intent,
                      '"intent": %s' % json.dumps(ps), 1)

    assert old_intent not in out, "old intent still present somewhere"

    os.makedirs("outputs", exist_ok=True)
    out_path = os.path.join("outputs",
                            "request_pilot_%s.txt" % inst["instance_id"])
    open(out_path, "w", encoding="utf-8", newline="\n").write(out)

    # diff report: verify each substitution explicitly (adjacent changes can
    # merge into one diff hunk, so hunk count alone is not the test)
    diff = list(difflib.unified_diff(text.splitlines(), out.splitlines(),
                                     lineterm="", n=0))
    hunks = sum(1 for l in diff if l.startswith("@@"))
    subs = [
        ("1 persona clause", out.count(NEW_PERSONA) == 1),
        ("2 domain parenthetical", out.count(NEW_DOMAIN) == 1),
        ("3 NOW-section intent", ('INTENT: "%s"' % ps) in out),
        ("4 schema intent string", ('"intent": %s' % json.dumps(ps)) in out),
    ]
    ok = all(v for _n, v in subs)
    print("wrote %s" % out_path)
    for name, v in subs:
        print("  substitution %-24s %s" % (name, "OK" if v else "MISSING"))
    print("old intent fully removed      %s" %
          ("OK" if old_intent not in out else "NO"))
    print("diff hunks: %d (3 is normal: substitutions 2 and 3 are adjacent "
          "lines and merge)" % hunks)
    nonascii = [(k, hex(ord(c))) for k, c in enumerate(out) if ord(c) > 127]
    print("non-ascii characters in output: %d %s" %
          (len(nonascii), "(inspect!)" if nonascii else ""))
    if not ok:
        sys.exit("ABORT: a substitution is missing; do not use the output")


if __name__ == "__main__":
    main()
