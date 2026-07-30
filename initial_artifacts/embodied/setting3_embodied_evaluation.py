import os
import re
import json

from langchain_anthropic import ChatAnthropic

INTENT = "clean_stovetop"
INTENT_NL = "Wipe the stovetop clean."
LOCATION = "kitchen stovetop"
REQUEST_FILE = "request_corrected_embodied.txt"   # the corrected Setting 3 prompt, in the same folder

# Ground-truth answer key (embodied tree, ground_truth_embodied.xlsx). id -> tuple fields + parent pointer.
# Temporal is "always" throughout: the turn-off-before-wipe ordering is a firing condition
# (monitored state), not a tuple field, per the policy model. The sequencing is carried
# structurally (P4.2 disable before P4.3 wipe). P6 is the safety-outranks-completion invariant.
POLICY_TREE = {
    "P0":   dict(level="declarative", parent=None, definer="human operator",  enforcer="Orchestrator", action="clean",     resource="stovetop surface",            spatial="stovetop workspace", temporal="always", context="household"),
    "P1":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Plan",         action="plan",      resource="task plan",                   spatial="stovetop workspace", temporal="always", context="household"),
    "P2":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Monitor",      action="perceive",  resource="scene (stovetop, burners, objects)", spatial="stovetop workspace", temporal="always", context="household"),
    "P2.1": dict(level="imperative",  parent="P2", definer="assurance engine", enforcer="Analyze",      action="resolve",   resource="burner state; surface temperature", spatial="stovetop",      temporal="always", context="household"),
    "P3":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Analyze",      action="detect",    resource="burner heat; hot surface",    spatial="stovetop",           temporal="always", context="household"),
    "P4":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Plan",         action="enforce",   resource="enforcement decision",        spatial="stovetop workspace", temporal="always", context="household"),
    "P4.1": dict(level="imperative",  parent="P4", definer="assurance engine", enforcer="Analyze",      action="check",     resource="burner state; surface temperature", spatial="stovetop",      temporal="always", context="household"),
    "P4.2": dict(level="imperative",  parent="P4", definer="assurance engine", enforcer="Execute",      action="disable",   resource="burner",                      spatial="stovetop",           temporal="always", context="household"),
    "P4.3": dict(level="imperative",  parent="P4", definer="assurance engine", enforcer="Execute",      action="wipe",      resource="stovetop surface",            spatial="stovetop",           temporal="always", context="household"),
    "P5":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Analyze",      action="verify",    resource="goal state (clean surface)",  spatial="stovetop",           temporal="always", context="household"),
    "P6":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Plan",         action="arbitrate", resource="safety vs completion",        spatial="stovetop workspace", temporal="always", context="household"),
}


def gt_path(pid):
    """Root-to-leaf policy path for a policy id, by following parent pointers."""
    path = []
    cur = pid
    while cur is not None:
        path.append(cur)
        cur = POLICY_TREE[cur]["parent"]
    return list(reversed(path))


def _model():
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("set ANTHROPIC_API_KEY before running")
    return ChatAnthropic(model="claude-sonnet-4-6", temperature=0, max_tokens=8192)


def _text(content):
    """Flatten a model response (str or list of content blocks) to plain text."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict):
            parts.append(block.get("text", ""))
        else:
            parts.append(str(block))
    return "".join(parts)


def run_setting2_unstructured():
    """Setting 2 - LangChain alone. Plain intent, no policy model, no forced format.
    Returns the raw free-text decomposition exactly as the model produces it."""
    prompt = (
        "You operate an embodied household robot.\n"
        f'The operator has given this intent: "{INTENT_NL}"\n'
        f"location = {LOCATION}\n\n"
        "Break this intent down into the policies the system should enforce to satisfy it. "
        "For each policy, state what it does and why it follows from the intent."
    )
    return _text(_model().invoke(prompt).content)


def _extract_json(text):
    """Pull the JSON object out of a reply that may wrap it in fences or prose."""
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    if not t.startswith("{"):
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end != -1:
            t = t[start:end + 1]
    return json.loads(t)


def run_setting3_structured():
    """Setting 3 - LangChain + policy model. Same task and intent as Setting 2,
    plus the corrected policy model and a forced tuple/JSON format (request_corrected_embodied.txt).
    Returns (raw_text, parsed_tree_or_None)."""
    with open(REQUEST_FILE, encoding="utf-8") as f:
        prompt = f.read()
    raw = _text(_model().invoke(prompt).content)
    try:
        parsed = _extract_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        parsed = None
        print(f"[warn] Setting 3 output was not parseable JSON: {e}")
    return raw, parsed


def main():
    s2 = run_setting2_unstructured()
    print("=== Setting 2: LangChain alone (unstructured refinement) ===\n")
    print(s2)
    with open("setting2_output_embodied.txt", "w", encoding="utf-8") as f:
        f.write(s2)

    s3_raw, s3_parsed = run_setting3_structured()
    print("\n\n=== Setting 3: LangChain + policy model (structured refinement) ===\n")
    print(s3_raw)
    with open("setting3_raw_embodied.txt", "w", encoding="utf-8") as f:
        f.write(s3_raw)
    if s3_parsed is not None:
        with open("setting3_output_embodied.json", "w", encoding="utf-8") as f:
            json.dump(s3_parsed, f, indent=2)
        n = len(s3_parsed.get("policies", []))
        print(f"\n\nparsed {n} policies -> setting3_output_embodied.json")

    print("\nwrote setting2_output_embodied.txt, setting3_raw_embodied.txt, setting3_output_embodied.json")


if __name__ == "__main__":
    main()
