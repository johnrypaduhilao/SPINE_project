"""Plan-stage runner, structured cell. Schema plan_structured/2.

Sends the built structured request (see build_structured_request.py) as one
call at temperature 0 and saves the returned policy tree. The response is
stored verbatim; a best-effort parse and structural checks (parent pointers
resolve, definers by level, rationale presence) are recorded next to it.
The checks are mechanical; manual scoring governs.

Run (PowerShell):
  python run_plan_structured.py --provider anthropic --request outputs\\request_structured_<id>.txt --dry-run
  python run_plan_structured.py --provider anthropic --request outputs\\request_structured_<id>.txt
  python run_plan_structured.py --provider openai --request outputs\\request_structured_<id>.txt

Requires ANTHROPIC_API_KEY or OPENAI_API_KEY in the environment.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time

OUT_DIR = "outputs"
TEMPERATURE = 0
MAX_TOKENS = 16000         # raised from 8000: reasoning-tier models spend
                           # hidden tokens inside the completion budget
SCHEMA_VERSION = "plan_structured/2"

DEFAULT_MODEL = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-5.6-terra",
}


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def merge_usage(usage, meta):
    if isinstance(meta, dict):
        for k, v in meta.items():
            if isinstance(v, int):
                usage[k] = max(usage.get(k, 0), v)
    return usage


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
    if usage:
        print("tokens (provider-reported): %s" % json.dumps(usage))
    if not text:
        sys.exit("no text came back%s"
                 % (": " + truncated if truncated else ""))
    return text, wall, outcome, truncated, temperature_dropped, usage


def parse_tree(text):
    """Best-effort parse. The RAW text is what gets stored either way."""
    body = text.strip()
    m = re.search(r"```(?:json)?\s*\n", body)
    if m and body.rfind("```") > m.end():
        body = body[m.end(): body.rfind("```")]
    body = body.strip()
    try:
        tree = json.loads(body)
        if not isinstance(tree, dict):
            return None, "top level is not a JSON object"
        return tree, None
    except Exception as e:
        return None, str(e)


def structural_checks(tree):
    """Mechanical facts only. Manual scoring governs."""
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["anthropic", "openai"],
                    required=True, help="no default, state it explicitly")
    ap.add_argument("--model", default=None)
    ap.add_argument("--request", required=True,
                    help="built request file from build_structured_request.py")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    model = args.model or DEFAULT_MODEL[args.provider]
    prompt = open(args.request, encoding="utf-8").read()
    m = re.search(r"request_structured_(.+)\.txt$",
                  os.path.basename(args.request))
    instance_id = m.group(1) if m else "unknown"

    print("schema_version  :", SCHEMA_VERSION)
    print("instance_id     :", instance_id)
    print("request sha256  :", sha256_text(prompt))

    if args.dry_run:
        print("\nDRY RUN: no call made. Request file validated and hashed.")
        return

    text, wall, outcome, truncated, temperature_dropped, usage = stream_call(
        prompt, args.provider, model)
    tree, err = parse_tree(text)
    struct = structural_checks(tree)

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "plan_structured_%s_%s_run%d.json"
                       % (instance_id, model, args.run))
    json.dump({
        "schema_version": SCHEMA_VERSION,
        "cell": "plan_structured",
        "instance_id": instance_id,
        "provider": args.provider,
        "model": model,
        "temperature": TEMPERATURE,
        "temperature_dropped": temperature_dropped,
        "usage_metadata": usage,
        "max_tokens": MAX_TOKENS,
        "run": args.run,
        "outcome": outcome,
        "truncated_reason": truncated,
        "request_sha256": sha256_text(prompt),
        "prompt": prompt,
        "response_text": text,
        "parsed_tree": tree,
        "parse_error": err,
        "structural_checks": struct,
        "wall_s": round(wall, 2),
    }, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("structured plan -> %s" % out)
    print("\nsaved: %s" % out)
    print("%d chars, outcome %s, %.1f s" % (len(text), outcome, wall))
    if err:
        print("JSON parse FAILED (%s). Raw text is stored; parse by hand."
              % err)
    else:
        print("structural checks (mechanical; manual scoring governs): %s"
              % json.dumps(struct))
    print("response_text is stored verbatim; clean only at quoting time")


if __name__ == "__main__":
    main()
