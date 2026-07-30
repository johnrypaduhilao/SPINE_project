"""
run_plan_unstructured.py

The unstructured plan cell of the 2x2. One request at temperature 0, no
tools, no repo access, no schema. Whatever prose comes back gets saved as-is.

Reason this cell had to exist: the pilot only had the executing agent (flat
trajectory, tools, real repo) and the structured plan (policy tree, one call,
no repo). Those two differ on modality and on representation at the same
time, so coverage numbers scored across them aren't comparing like with like.
With this cell in place, recall/precision/SIF get scored plan against plan
and representation is the only thing that moves. Nothing about the executing
agent changes; it stays the task-performance baseline for % Resolved once we
get to the Docker stage.

Kept word for word from the structured request: the persona sentence, the
domain parenthetical, the intent, the decompose-first instruction, and the
word "policies". Taken out: the POLICY MODEL tuple block, the abstraction
levels, the refinement rules, parent_id, definer, enforcer, the rationale
requirement, the worked example, the JSON schema. The rule I followed was to
keep vocabulary that describes the object and drop vocabulary that describes
the representation. Dropping the schema and the worked example isn't a
confound, it's the manipulation, since the example's content is the format.

Copied the mechanics from run_pilot_request.py (the Gemini generation, which
this merges back into): streaming with partial capture, an outcome value in
the artifact, provenance in the output, plain-terms summary at the end.

Run (PowerShell):
  $env:GOOGLE_API_KEY="..."     or    $env:ANTHROPIC_API_KEY="..."
  python run_plan_unstructured.py --provider google    --instance-json <path>
  python run_plan_unstructured.py --provider anthropic --instance-json <path>

Dry run (no API key, no call; builds and prints the prompt only):
  python run_plan_unstructured.py --provider google --instance-json <path> --dry-run

Each call costs a bit of money, so don't loop it. Scoring is manual; the
checks in here are only the reproducibility layer.
"""

import argparse
import hashlib
import json
import os
import sys
import time

OUT_DIR = "outputs"
TEMPERATURE = 0
MAX_TOKENS = 8000          # same ceiling run_pilot_request.py uses, both arms
SCHEMA_VERSION = "plan_unstructured/1"

DEFAULT_MODEL = {
    "google": "gemini-3.5-flash",
    "anthropic": "claude-sonnet-4-6",
}

INTENT_TOKEN = "{{INTENT}}"

# Persona sentence and domain parenthetical are pasted straight out of
# request_pilot_astropy__astropy-12907.txt, character for character, hard wrap
# after "natural-language" and leading spaces on the domain line included.
# The only two changes: "a tree of structured policies" -> "a set of
# policies", "imperative, executable policies" -> "concrete, executable
# policies". Tree/structured/imperative are representation words, so they go.
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

# Word counts, not scores. They're here so that "those fields don't exist in
# this representation" is something a reader can check instead of just taking
# my word for it. TC/AC/EF are still scored by hand.
PROBE_TERMS = [
    "parent", "definer", "enforcer", "policy", "declarative", "definitive",
    "imperative", "rationale", "spatial", "temporal", "resource",
]


def build_prompt(problem_statement):
    """One substitution only, and print enough to prove it went in clean."""
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
    """Stream it and hang on to whatever arrives.

    Same thinking as in run_pilot_request.py. If the token budget runs out or
    the stream drops halfway through, the partial text is still the artifact I
    came for, and I'd rather not lose it to a blocking call that raises. A
    truncated plan is a result too, it just gets recorded as one.
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
    except Exception as e:                       # don't drop what we already got
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