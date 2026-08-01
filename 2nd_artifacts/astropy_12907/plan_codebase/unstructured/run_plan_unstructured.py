"""Plan-stage runner, unstructured cell. Schema plan_unstructured/2.

One request at temperature 0, no tools, no repo access, no output schema.
The response is stored verbatim. Manual scoring governs; everything printed
here is a reproducibility layer only.

Run (PowerShell):
  python run_plan_unstructured.py --provider anthropic --instance-json <path> --dry-run
  python run_plan_unstructured.py --provider anthropic --instance-json <path>
  python run_plan_unstructured.py --provider openai --instance-json <path>

Requires ANTHROPIC_API_KEY or OPENAI_API_KEY in the environment.
"""

import argparse
import hashlib
import json
import os
import sys
import time

OUT_DIR = "outputs"
TEMPERATURE = 0
MAX_TOKENS = 16000         # raised from 8000: reasoning-tier models spend
                           # hidden tokens inside the completion budget
SCHEMA_VERSION = "plan_unstructured/2"

DEFAULT_MODEL = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-5.6-terra",
}

INTENT_TOKEN = "{{INTENT}}"

PREFIX = (
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

TEMPLATE = PREFIX

STUB_INSTANCE = {
    "instance_id": "STUB__example-0001",
    "problem_statement": (
        "Division by zero crashes the calculator. Calling divide(1, 0) "
        "raises an unhandled ZeroDivisionError; it should raise a "
        "CalculatorError with a clear message instead."
    ),
}

# Presence counts, not scores. Manual scoring governs TC/AC/EF.
PROBE_TERMS = [
    "parent", "definer", "enforcer", "policy", "declarative", "definitive",
    "imperative", "rationale", "spatial", "temporal", "resource",
]


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def merge_usage(usage, meta):
    if isinstance(meta, dict):
        for k, v in meta.items():
            if isinstance(v, int):
                usage[k] = max(usage.get(k, 0), v)
    return usage


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
    print("  prefix sha256   : %s" % sha256_text(PREFIX))
    print("  template sha256 : %s" % sha256_text(TEMPLATE))
    print("  prompt sha256   : %s" % sha256_text(prompt))
    return prompt


def make_llm(provider, model, drop_temperature=False):
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, temperature=TEMPERATURE,
                             max_tokens=MAX_TOKENS)
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        kwargs = {"model": model, "max_tokens": MAX_TOKENS}
        if not drop_temperature:
            kwargs["temperature"] = TEMPERATURE
        try:
            return ChatOpenAI(stream_usage=True, **kwargs)
        except TypeError:
            return ChatOpenAI(**kwargs)
    sys.exit("unknown provider: %s" % provider)


def stream_once(llm, prompt):
    parts, truncated, usage = [], None, {}
    t0 = time.perf_counter()
    try:
        for chunk in llm.stream(prompt):
            merge_usage(usage, getattr(chunk, "usage_metadata", None))
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
    return "".join(parts).strip(), wall, truncated, usage


def stream_call(prompt, provider, model):
    """Stream and keep whatever arrives. A truncated response is still the
    artifact; it gets recorded as one. If the model rejects temperature=0
    (some reasoning models do), retry once without it and record the drop."""
    temperature_dropped = False
    print("streaming from %s / %s (temperature %s) ..."
          % (provider, model, TEMPERATURE), flush=True)
    text, wall, truncated, usage = stream_once(
        make_llm(provider, model), prompt)
    if (not text and truncated and provider == "openai"
            and "temperature" in truncated.lower()):
        temperature_dropped = True
        print("temperature rejected; retrying without it", flush=True)
        text, wall, truncated, usage = stream_once(
            make_llm(provider, model, drop_temperature=True), prompt)
    outcome = "stream_cut_short" if truncated else "completed"
    print("received %d chars in %.1f s%s"
          % (len(text), wall, " (stream cut short)" if truncated else ""))
    if not text:
        sys.exit("no text came back%s"
                 % (": " + truncated if truncated else ""))
    if usage:
        print("tokens (provider-reported): %s" % json.dumps(usage))
    return text, wall, outcome, truncated, temperature_dropped, usage


def probe(text):
    low = text.lower()
    return {t: low.count(t) for t in PROBE_TERMS}


def summarize(text, wall, outcome, counts, out):
    lines = [l for l in text.splitlines() if l.strip()]
    print("\nsaved: %s" % out)
    print("%d chars, %d non-empty lines, outcome %s, %.1f s"
          % (len(text), len(lines), outcome, wall))
    print("term presence counts (not scores; manual scoring governs): %s"
          % json.dumps({k: v for k, v in counts.items() if v}))
    print("response_text is stored verbatim; clean only at quoting time")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["anthropic", "openai"],
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

    text, wall, outcome, truncated, temperature_dropped, usage = stream_call(
        prompt, args.provider, model)
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
        "temperature_dropped": temperature_dropped,
        "usage_metadata": usage,
        "max_tokens": MAX_TOKENS,
        "run": args.run,
        "outcome": outcome,
        "truncated_reason": truncated,
        "prefix_sha256": sha256_text(PREFIX),
        "template_sha256": sha256_text(TEMPLATE),
        "prompt_sha256": sha256_text(prompt),
        "prompt": prompt,
        "task": problem_statement,
        "response_text": text,
        "wall_s": round(wall, 2),
        "structure_probe": counts,
    }, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("unstructured plan -> %s" % out)
    summarize(text, wall, outcome, counts, out)


if __name__ == "__main__":
    main()
