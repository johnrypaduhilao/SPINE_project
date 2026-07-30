import os
import re
import json

from langchain_anthropic import ChatAnthropic

INTENT = "protect_files(/srv/app/config)"
INTENT_NL = "Protect the sensitive files at this path."
PROTECTED_PATH = "/srv/app/config"
REQUEST_FILE = "request_corrected.txt"   # the corrected Setting 3 prompt, in the same folder

# Ground-truth answer key (Table 1). id -> tuple fields + parent pointer.
POLICY_TREE = {
    "P0":   dict(level="declarative", parent=None, definer="human operator",  enforcer="Orchestrator", action="protect",   resource="file",                       spatial="/srv/app/config",                    temporal="always", context="production"),
    "P1":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Analyze",      action="classify",  resource="file",                       spatial="/srv/app/config",                    temporal="always", context="production"),
    "P1.1": dict(level="imperative",  parent="P1", definer="assurance engine", enforcer="Execute",      action="tag",       resource="file",                       spatial="/srv/app/config",                    temporal="always", context="production"),
    "P2":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Monitor",      action="monitor",   resource="file operation",             spatial="/srv/app/config",                    temporal="always", context="production"),
    "P2.1": dict(level="definitive",  parent="P2", definer="assurance engine", enforcer="Analyze",      action="authorize", resource="operation; actor",           spatial="/srv/app/config",                    temporal="always", context="production"),
    "P3":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Plan",         action="decide",    resource="read/copy/move operation",   spatial="/srv/app/config",                    temporal="always", context="production"),
    "P3.1": dict(level="imperative",  parent="P3", definer="assurance engine", enforcer="Execute",      action="block",     resource="read operation",             spatial="/srv/app/config",                    temporal="always", context="production"),
    "P3.2": dict(level="imperative",  parent="P3", definer="assurance engine", enforcer="Execute",      action="block",     resource="copy operation",             spatial="/srv/app/config -> external",        temporal="always", context="production"),
    "P3.3": dict(level="imperative",  parent="P3", definer="assurance engine", enforcer="Execute",      action="block",     resource="move operation",             spatial="/srv/app/config -> external",        temporal="always", context="production"),
    "P4":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Plan",         action="decide",    resource="write/permission operation", spatial="/srv/app/config",                    temporal="always", context="production"),
    "P4.1": dict(level="imperative",  parent="P4", definer="assurance engine", enforcer="Execute",      action="block",     resource="write operation",            spatial="/srv/app/config",                    temporal="always", context="production"),
    "P4.2": dict(level="imperative",  parent="P4", definer="assurance engine", enforcer="Execute",      action="block",     resource="permission change",          spatial="/srv/app/config",                    temporal="always", context="production"),
    "P5":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Plan",         action="decide",    resource="delete operation",           spatial="/srv/app/config",                    temporal="always", context="production"),
    "P5.1": dict(level="imperative",  parent="P5", definer="assurance engine", enforcer="Execute",      action="block",     resource="delete operation",           spatial="/srv/app/config",                    temporal="always", context="production"),
    "P6":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Analyze",      action="detect",    resource="resolved target",            spatial="/srv/app/config & resolved targets", temporal="always", context="production"),
    "P6.1": dict(level="imperative",  parent="P6", definer="assurance engine", enforcer="Execute",      action="reject",    resource="resolved target",            spatial="outside /srv/app/config",            temporal="always", context="production"),
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
    return ChatAnthropic(model="claude-sonnet-4-6", temperature=0, max_tokens=4096)


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
        "You operate an autonomous coding agent.\n"
        f'The operator has given this intent: "{INTENT_NL}"\n'
        f"path = {PROTECTED_PATH}\n\n"
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
    plus the corrected policy model and a forced tuple/JSON format (request_corrected.txt).
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
    with open("setting2_output.txt", "w", encoding="utf-8") as f:
        f.write(s2)

    s3_raw, s3_parsed = run_setting3_structured()
    print("\n\n=== Setting 3: LangChain + policy model (structured refinement) ===\n")
    print(s3_raw)
    with open("setting3_raw.txt", "w", encoding="utf-8") as f:
        f.write(s3_raw)
    if s3_parsed is not None:
        with open("setting3_output.json", "w", encoding="utf-8") as f:
            json.dump(s3_parsed, f, indent=2)
        n = len(s3_parsed.get("policies", []))
        print(f"\n\nparsed {n} policies -> setting3_output.json")

    print("\nwrote setting2_output.txt, setting3_raw.txt, setting3_output.json")


if __name__ == "__main__":
    main()