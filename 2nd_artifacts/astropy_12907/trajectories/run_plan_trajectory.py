"""
run_plan_trajectory.py

The TRAJECTORY PLAN cell. Third representation in the plan stage, alongside
plan_unstructured (prose) and plan_structured (policy tree).

Why this cell exists. Comparing prose against a policy tree leaves one
objection open: unstructured prose is a weak comparator, because the actual
state of practice in agentic software engineering is the SWE-agent
thought / action / observation trajectory, which IS structured. A reviewer can
say the schema beat free text and that proves nothing about lineage.

This cell closes that. The trajectory format has fields but carries no parent
pointer and no definer:

    representation      fields   lineage
    prose               no       no
    trajectory          yes      no
    policy tree         yes      yes

So the claim under test narrows from "structure helps" to "LINEAGE-BEARING
structure is what makes audit a traversal", which is the actual contribution.

WHAT TO EXPECT, recorded before the run so it is a prediction and not a
rationalization. The trajectory carries a thought field on every step, so
reasoning IS anchored to a step and EF may score above 0.00, possibly 1.00.
If that happens the honest reading is that EF was not measuring anything
independent of TC, and the claim narrows cleanly to TC and AC. AC stays 0.00
regardless: no trajectory format has a definer field. Finding this with a run
is much better than having a reviewer find it.

CONTROLLED COMPARISON. Held identical to run_plan_unstructured.py: the persona
sentence, the domain parenthetical, the intent, the decompose instruction, and
the object vocabulary ("policies"). ONLY the output format block differs. That
makes plan_unstructured vs plan_trajectory a pure format manipulation with
exactly one variable.

FIELD NAMES ARE NOT INVENTED. thought / action / observation with action as
{name, args} is lifted from the project's own banked exec artifacts
(unstructured_trajectory_astropy12907_run1.json), which is also the format the
SWE-agent and Overthinking papers report. The four tool names are the same four
the exec harness exposes. Observation is deliberately omitted from a PLAN,
because observations only exist once something has run; expected_observation is
requested instead and is clearly labelled as an expectation.

DESIGN NOTE, disclose it: giving a fixed action vocabulary is symmetric with
the structured request, which likewise constrains enforcer to a fixed set. It
also makes this plan directly executable later as exec_trajectory_plan without
a translation step.

Run (PowerShell):
  python run_plan_trajectory.py --provider anthropic --instance-json <path> --dry-run
  python run_plan_trajectory.py --provider anthropic --instance-json <path>
"""

import argparse
import hashlib
import json
import os
import sys
import time

OUT_DIR = "outputs"
TEMPERATURE = 0
MAX_TOKENS = 8000          # same ceiling as the other two plan cells
SCHEMA_VERSION = "plan_trajectory/1"

DEFAULT_MODEL = {
    "google": "gemini-3.5-flash",
    "anthropic": "claude-sonnet-4-6",
}

INTENT_TOKEN = "{{INTENT}}"

# Lines 1 to 8 are character-identical to run_plan_unstructured.py. Only the
# OUTPUT FORMAT block below them differs.
TEMPLATE = (
    "You operate a policy-refinement agent that governs a software-repository "
    "issue-resolution workspace. Refine a single high-level natural-language\n"
    "intent into a set of policies.\n"
    "\n"
    "INTENT: \"" + INTENT_TOKEN + "\"\n"
    "        (domain: code-execution agent resolving a repository issue)\n"
    "\n"
    "Decompose the intent into its sub-goals first, then refine each toward\n"
    "concrete, executable policies.\n"
    "\n"
    "OUTPUT FORMAT\n"
    "Emit each policy as one step of an agent trajectory. Return a JSON array\n"
    "of step objects and nothing else. Each step object has exactly these\n"
    "fields:\n"
    "\n"
    "  thought               your reasoning for taking this step\n"
    "  action                an object with:\n"
    "                          name  one of: search_repo, open_file,\n"
    "                                edit_file, done\n"
    "                          args  an object of arguments for that tool\n"
    "  expected_observation  what you expect this step to return\n"
    "\n"
    "Order the steps by execution order.\n"
)

STUB_INSTANCE = {
    "instance_id": "STUB__example-0001",
    "problem_statement": (
        "Division by zero crashes the calculator. Calling divide(1, 0) "
        "raises an unhandled ZeroDivisionError; it should raise a "
        "CalculatorError with a clear message instead."
    ),
}

# Mechanical presence counts, NOT scores. Manual scoring governs TC/AC/EF.
PROBE_TERMS = [
    "parent", "definer", "enforcer", "policy", "declarative", "definitive",
    "imperative", "rationale", "spatial", "temporal", "resource",
]

TOOLS = ["search_repo", "open_file", "edit_file", "done"]


def build_prompt(problem_statement):
    if TEMPLATE.count(INTENT_TOKEN) != 1:
        sys.exit("template must contain exactly one %s" % INTENT_TOKEN)
    prompt = TEMPLATE.replace(INTENT_TOKEN, problem_statement)
    print("substitution proof")
    print("  template chars  : %d" % len(TEMPLATE))
    print("  intent chars    : %d" % len(problem_statement))
    print("  prompt chars    : %d" % len(prompt))
    print("  intent verbatim : %s" % (problem_statement in prompt))
    print("  token remaining : %s" % (INTENT_TOKEN in prompt))
    print("  crlf remaining  : %s" % ("\r\n" in prompt))
    print("  prompt sha256   : %s"
          % hashlib.sha256(prompt.encode("utf-8")).hexdigest())
    return prompt


def make_llm(provider, model):
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, temperature=TEMPERATURE,
                                      max_tokens=MAX_TOKENS)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, temperature=TEMPERATURE,
                             max_tokens=MAX_TOKENS)
    sys.exit("unknown provider: %s" % provider)


def stream_call(prompt, provider, model):
    """Stream and keep whatever arrives, same pattern as the other plan cells."""
    llm = make_llm(provider, model)
    parts, truncated = [], None
    print("streaming from %s / %s (temperature %s) ..."
          % (provider, model, TEMPERATURE), flush=True)
    t0 = time.perf_counter()
    try:
        for chunk in llm.stream(prompt):
            c = chunk.content
            if not isinstance(c, str):
                c = " ".join(b.get("text", "") for b in c
                             if isinstance(b, dict))
            if c:
                parts.append(c)
                print(".", end="", flush=True)
    except Exception as e:
        truncated = str(e)
    wall = time.perf_counter() - t0
    print()
    text = "".join(parts).strip()
    outcome = "stream_cut_short" if truncated else "completed"
    print("received %d chars in %.1f s%s"
          % (len(text), wall, " (stream cut short)" if truncated else ""))
    if not text:
        sys.exit("no text came back%s"
                 % (": " + truncated if truncated else ""))
    return text, wall, outcome, truncated


def parse_steps(text):
    """Best-effort parse. The RAW text is what gets stored either way."""
    body = text.strip()
    if body.startswith("```"):
        body = body.split("```")[1]
        if body.lstrip().lower().startswith("json"):
            body = body.lstrip()[4:]
    body = body.strip()
    try:
        steps = json.loads(body)
        if not isinstance(steps, list):
            return None, "top level is not a JSON array"
        return steps, None
    except Exception as e:
        return None, str(e)


def audit(steps):
    """Structural facts only. Not a score."""
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
                                ("parent" in k.lower() for k in s)
                                for s in steps),
        "has_definer_field": any(isinstance(s, dict) and
                                 any("definer" in k.lower() for k in s)
                                 for s in steps),
    }


def summarize(text, wall, outcome, counts, struct, out, err):
    print("\nWHAT THIS RUN DID (plain terms):")
    print("  Asked for the SAME policies as the prose cell, emitted as agent")
    print("  trajectory steps. Fields, but no parent pointer and no definer.")
    print("  Saved to %s. %d chars, outcome %s, %.1f s."
          % (out, len(text), outcome, wall))
    if err:
        print("  JSON parse FAILED (%s). Raw text is stored; parse by hand." % err)
    else:
        print("  Structure: %s" % json.dumps(struct))
    print("  Word counts: %s" % json.dumps({k: v for k, v in counts.items() if v}))
    print("  Counts are not scores. Manual scoring governs.")
    print("\nREADING CHECKS (by hand, before scoring):")
    print("  1. Does every step carry a thought? If yes, EF may score above")
    print("     0.00 for this representation. That is the predicted outcome,")
    print("     not a surprise; record it and let the claim narrow to TC/AC.")
    print("  2. Is there ANY field linking a step to a parent step? There")
    print("     should not be. If the model invented one, that is a finding,")
    print("     same as the prose cell inventing a dependency diagram.")
    print("  3. Is there a definer anywhere? There should not be. AC = 0.00.")
    print("  4. Does it cover the six answer-key obligations?")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["google", "anthropic"],
                    required=True, help="no default, state it explicitly")
    ap.add_argument("--model", default=None)
    ap.add_argument("--instance-json", default=None)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stub", action="store_true", help="implies --dry-run")
    args = ap.parse_args()

    model = args.model or DEFAULT_MODEL[args.provider]
    dry = args.dry_run or args.stub

    if args.stub:
        instance = STUB_INSTANCE
    else:
        if not args.instance_json:
            sys.exit("needs --instance-json (or --stub)")
        instance = json.load(open(args.instance_json, encoding="utf-8"))

    problem_statement = instance["problem_statement"].replace("\r\n", "\n")
    prompt = build_prompt(problem_statement)

    if dry:
        print("\nDRY RUN: no call made. Nothing below is a result.")
        print("-" * 72)
        print(prompt)
        print("-" * 72)
        return

    text, wall, outcome, truncated = stream_call(prompt, args.provider, model)
    steps, err = parse_steps(text)
    struct = audit(steps)
    low = text.lower()
    counts = {t: low.count(t) for t in PROBE_TERMS}

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "plan_trajectory_%s_%s_run%d.json"
                       % (instance.get("instance_id", "unknown"), model,
                          args.run))
    json.dump({
        "schema_version": SCHEMA_VERSION,
        "cell": "plan_trajectory",
        "instance_id": instance.get("instance_id"),
        "provider": args.provider,
        "model": model,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "run": args.run,
        "outcome": outcome,
        "truncated_reason": truncated,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt": prompt,
        "task": problem_statement,
        "response_text": text,
        "parsed_steps": steps,
        "parse_error": err,
        "structure_audit": struct,
        "wall_s": round(wall, 2),
        "structure_probe": counts,
    }, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("trajectory plan -> %s" % out)
    summarize(text, wall, outcome, counts, struct, out, err)
    print("\nresponse_text is stored VERBATIM. Do not clean it here; clean "
          "only at quoting time.")


if __name__ == "__main__":
    main()
