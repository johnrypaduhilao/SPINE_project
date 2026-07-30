import os
import json

from langchain_anthropic import ChatAnthropic

INTENT = "clean_stovetop"
INTENT_NL = "Wipe the stovetop clean."
LOCATION = "kitchen stovetop"

# Ground-truth answer key (embodied tree, ground_truth_embodied.xlsx). id -> tuple fields + parent pointer.
# Temporal is "always" throughout: the turn-off-before-wipe ordering is a firing condition
# (monitored state), not a tuple field, per the policy model. The sequencing is carried
# structurally (P4.2 disable before P4.3 wipe). P6 is the safety-outranks-completion invariant.
POLICY_TREE = {
    "P0":   dict(level="declarative", parent=None, definer="human operator",  enforcer="Orchestrator", action="clean",     resource="stovetop surface",            spatial="stovetop workspace", temporal="always", context="household"),
    "P1":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Plan",         action="plan",      resource="task plan",                   spatial="stovetop workspace", temporal="always", context="household"),
    "P2":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Monitor",      action="perceive",  resource="scene (stovetop, burners, objects)", spatial="stovetop workspace", temporal="always", context="household"),
    "P2.1": dict(level="definitive",  parent="P2", definer="assurance engine", enforcer="Analyze",      action="resolve",   resource="burner state; surface temperature", spatial="stovetop",      temporal="always", context="household"),
    "P3":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Analyze",      action="detect",    resource="burner heat; hot surface",    spatial="stovetop",           temporal="always", context="household"),
    "P4":   dict(level="definitive",  parent="P0", definer="assurance engine", enforcer="Plan",         action="enforce",   resource="enforcement decision",        spatial="stovetop workspace", temporal="always", context="household"),
    "P4.1": dict(level="definitive",  parent="P4", definer="assurance engine", enforcer="Analyze",      action="check",     resource="burner state; surface temperature", spatial="stovetop",      temporal="always", context="household"),
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
    return ChatAnthropic(model="claude-sonnet-4-6", temperature=0, max_tokens=2048)


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


def main():
    output = run_setting2_unstructured()
    print("=== Setting 2: LangChain alone (unstructured refinement) ===\n")
    print(output)
    with open("setting2_output_embodied.txt", "w", encoding="utf-8") as f:
        f.write(output)
    print("\n\nwrote setting2_output_embodied.txt")


if __name__ == "__main__":
    main()
