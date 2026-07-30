import sys
import json
import datetime

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

AV_INTENT = "Cap the vehicle's speed at 30 km/h when there is fog or rain."

ANSWER_KEY = {
    "GT-01": "determine the posted speed limit (P1 / P1.1 read from map)",
    "GT-02": "detect fog or rain, the trigger (P2.1)",
    "GT-03": "determine the 30 km/h weather cap (P2)",
    "GT-04": "compute the effective cap as the tighter of posted and weather limits (P3.1)",
    "GT-05": "scope the cap across all lanes, not just the ego or fast lane (P3)",
    "GT-06": "decelerate smoothly to the cap (P3.3)",
    "GT-07": "block acceleration above the cap (P3.2)",
}

SETTING2_PROMPT = (
    "You operate an autonomous driving agent. The operator has given this intent: "
    "\"Cap the vehicle's speed at 30 km/h when there is fog or rain.\" "
    "Break this intent down into the policies the system should enforce to satisfy it. "
    "For each policy, state what it does and why it follows from the intent."
)

SETTING3_FILE = "request_corrected_av.txt"


def _model():
    return ChatAnthropic(model=MODEL, temperature=0, max_tokens=MAX_TOKENS)


def _extract_json(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1:
        t = t[start:end + 1]
    return json.loads(t)


def run_setting2():
    resp = _model().invoke([HumanMessage(content=SETTING2_PROMPT)])
    text = resp.content if isinstance(resp.content, str) else str(resp.content)
    with open("setting2_output_av.txt", "w", encoding="utf-8") as f:
        f.write(text)
    print("Setting 2 (unstructured) written to setting2_output_av.txt")
    return text


def run_setting3():
    with open(SETTING3_FILE, encoding="utf-8") as f:
        prompt = f.read()
    resp = _model().invoke([HumanMessage(content=prompt)])
    raw = resp.content if isinstance(resp.content, str) else str(resp.content)
    with open("setting3_raw_av.txt", "w", encoding="utf-8") as f:
        f.write(raw)
    try:
        parsed = _extract_json(raw)
    except Exception as e:
        print("Setting 3: JSON parse failed:", e)
        print("Raw output saved to setting3_raw_av.txt for inspection.")
        return None
    with open("setting3_output_av.json", "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2)
    print("Setting 3 (structured) written to setting3_output_av.json")
    return parsed


def structural_stats(parsed):
    if not parsed or "policies" not in parsed:
        return
    pols = parsed["policies"]
    ids = {p.get("id") for p in pols}
    n = len(pols)
    with_parent = sum(1 for p in pols if p.get("parent_id"))
    with_definer = sum(1 for p in pols if p.get("definer"))
    resolvable = sum(1 for p in pols if p.get("parent_id") in ids)
    non_root = sum(1 for p in pols if p.get("parent_id") is not None)

    def depth(p):
        d, cur, guard = 0, p, 0
        by_id = {x.get("id"): x for x in pols}
        while cur and cur.get("parent_id") and guard < 50:
            cur = by_id.get(cur.get("parent_id"))
            d += 1
            guard += 1
        return d

    max_depth = max((depth(p) for p in pols), default=0)
    print()
    print("Setting 3 structural stats (manual content scoring is separate):")
    print("  policies:                  ", n)
    print("  with parent pointer:       ", with_parent, "/", n)
    print("  with definer:              ", with_definer, "/", n)
    print("  parent resolvable in tree: ", resolvable, "/", non_root, "(non-root)")
    print("  max depth (root to leaf):  ", max_depth)


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    print("AV three-setting run -", datetime.datetime.now().isoformat(timespec="seconds"))
    print("Intent:", AV_INTENT)
    print("Answer key:", len(ANSWER_KEY), "steps (GT-01..GT-07)")
    print()
    parsed = None
    if which in ("all", "s2"):
        run_setting2()
    if which in ("all", "s3"):
        parsed = run_setting3()
    if parsed:
        structural_stats(parsed)


if __name__ == "__main__":
    main()
