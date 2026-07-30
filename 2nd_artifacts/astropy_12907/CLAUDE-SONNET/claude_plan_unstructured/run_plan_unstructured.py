"""
run_plan_unstructured.py

The UNSTRUCTURED PLAN cell of the 2x2. Sends one request (temperature 0),
no tools, no repository access, no schema, and saves whatever prose comes
back, verbatim.

Why this cell exists. The pilot already has an executing agent (flat
trajectory, tools, real repo) and a structured plan (policy tree, one call,
no repo). Those differ on two axes at once, modality and representation, so
coverage metrics scored across them are not like for like. This fills the
missing cell so recall, precision and SIF are scored plan against plan with
representation as the only variable. The executing agent is unaffected and
remains the task-performance baseline for % Resolved at the Docker stage.

What is held constant against the structured request, and what is removed.
KEPT VERBATIM : the persona sentence, the domain parenthetical, the intent,
                the decompose-first instruction, the word "policies".
REMOVED       : the POLICY MODEL tuple block, the abstraction levels, the
                refinement rules, parent_id, definer, enforcer, the rationale
                requirement, the worked example, and the JSON schema.
The rule is that the vocabulary of the OBJECT stays and the vocabulary of the
REPRESENTATION goes. Removing the schema and the worked example is not a
confound; it is the manipulation. The example's content IS the format.

Patterns inherited from run_pilot_request.py (the Gemini generation, which is
the merge target): streaming with partial capture, an outcome value written
into the artifact, full provenance in the output, and a plain-terms summary.

Run (PowerShell):
  $env:GOOGLE_API_KEY="..."     or    $env:ANTHROPIC_API_KEY="..."
  python run_plan_unstructured.py --provider google    --instance-json <path>
  python run_plan_unstructured.py --provider anthropic --instance-json <path>

Dry run (no API key, no call; builds and prints the prompt only):
  python run_plan_unstructured.py --provider google --instance-json <path> --dry-run

One call costs a modest amount; do not loop it. Manual scoring governs; the
checks here are the reproducibility layer only.
"""

import argparse
import hashlib
import json
import os
import sys
import time

OUT_DIR = "outputs"
TEMPERATURE = 0
MAX_TOKENS = 8000          # same ceiling as run_pilot_request.py, both arms
SCHEMA_VERSION = "plan_unstructured/1"

DEFAULT_MODEL = {
    "google": "gemini-3.5-flash",
    "anthropic": "claude-sonnet-4-6",
}

INTENT_TOKEN = "{{INTENT}}"

# The persona sentence and the domain parenthetical are copied character for
# character out of request_pilot_astropy__astropy-12907.txt, including the
# hard wrap after "natural-language" and the leading spaces on the domain
# line. Only "a tree of structured policies" becomes "a set of policies", and
# "imperative, executable policies" becomes "concrete, executable policies",
# because tree, structured and imperative are representation vocabulary.
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
)

STUB_INSTANCE = {
    "instance_id": "STUB__example-0001",
    "problem_statement": (
        "Division by zero crashes the calculator. Calling divide(1, 0) "
        "raises an unhandled ZeroDivisionError; it should raise a "
        "CalculatorError with a clear message instead."
    ),
}

# Mechanical presence counts, NOT scores. These exist so the claim "those
# fields do not exist in this representation" is checkable rather than
# asserted. Manual scoring governs TC/AC/EF.
PROBE_TERMS = [
    "parent", "definer", "enforcer", "policy", "declarative", "definitive",
    "imperative", "rationale", "spatial", "temporal", "resource",
]


def build_prompt(problem_statement):
    """Exactly one substitution, with per-substitution proof printed."""
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
    print("  intent first 60 : %s" % problem_statement[:60].replace("\n", " "))
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
    """Stream and keep whatever arrives.

    Same reasoning as run_pilot_request.py: if the token budget runs out or
    the stream drops mid-answer, the partial text is the artifact we came
    for. Losing it to one failed blocking call is the wrong outcome, and a
    truncated plan is itself a recordable result.
    """
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
    except Exception as e:                       # keep the partial answer
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


def probe(text):
    low = text.lower()
    return {t: low.count(t) for t in PROBE_TERMS}


def summarize(text, wall, outcome, counts, out):
    lines = [l for l in text.splitlines() if l.strip()]
    print("\nWHAT THIS RUN DID (plain terms):")
    print("  Sent one request with NO schema and NO worked example, and")
    print("  streamed the answer back as ordinary prose. Saved to %s." % out)
    print("  %d characters, %d non-empty lines, outcome %s, %.1f s."
          % (len(text), len(lines), outcome, wall))
    print("  Then counted words only: %s"
          % json.dumps({k: v for k, v in counts.items() if v}))
    print("  Those are presence counts, not scores. Nothing here judges")
    print("  whether the plan is any good, and nothing here scores TC, AC")
    print("  or EF. Manual scoring governs.")
    print("\nREADING CHECKS (by hand, before anything else):")
    print("  1. Does it cover the six answer-key obligations, or drift?")
    print("  2. Did it self-structure anyway (numbered items with parent")
    print("     references)? If so that is a FINDING, not a failure, and")
    print("     it must be recorded before scoring.")
    print("  3. Is any reasoning present but unanchored to a named policy?")
    print("     That is the EF=0 case: reasoning recorded, not recoverable.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["google", "anthropic"],
                    required=True, help="no default, state it explicitly")
    ap.add_argument("--model", default=None,
                    help="defaults to the provider's project-convention model")
    ap.add_argument("--instance-json", default=None,
                    help="instance file from fetch_swebench_lite.py --save")
    ap.add_argument("--run", type=int, default=1,
                    help="run index; pass@k writes run 2, 3, ...")
    ap.add_argument("--dry-run", action="store_true",
                    help="build and print the prompt, make no call")
    ap.add_argument("--stub", action="store_true",
                    help="use the fake instance; implies --dry-run")
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
    counts = probe(text)

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "plan_unstructured_%s_%s_run%d.json"
                       % (instance.get("instance_id", "unknown"), model,
                          args.run))
    json.dump({
        "schema_version": SCHEMA_VERSION,
        "cell": "plan_unstructured",
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
        "wall_s": round(wall, 2),
        "structure_probe": counts,
    }, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("unstructured plan -> %s" % out)
    summarize(text, wall, outcome, counts, out)
    print("\nresponse_text is stored VERBATIM. Do not clean it here; clean "
          "only at quoting time.")


if __name__ == "__main__":
    main()