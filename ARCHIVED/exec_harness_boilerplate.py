"""
exec_harness.py

Execute arm, stage 7. Skeleton; stub-verified, no live run yet.

Design (see pipeline_execute_arm.png): one harness, one budget
(MAX_TURNS=30), one record schema, temperature 0. The plan handed to the
agent is the only variable.

Configs (--config):
  noplan             no plan given                (banked run exists already)
  unstructured_plan  prose plan in the prompt
  trajectory_plan    trajectory-step plan in the prompt   (conditional)
  structured_plan    policy tree in the prompt

Every step emits one record with the same fields in every config:
  step_id, action, observation, timestamp, policy_id, provenance_mode

policy_id is filled at emit time only in structured_plan, where the prompt
asks the agent to name the policy id it is executing on each tool call.
Elsewhere the field stays null and provenance_mode is "reconstructed":
attribution is done afterwards by reading the log against the plan, which
is the O(n) side of the comparison. Same schema throughout; only whether
the field can be filled differs.

Gate is off for run 1. Delivery actions (git commit, push, PR) are not
blocked - the sandbox has no network - but the harness records what a gate
would have vetoed (gate_flag). A recorded veto shows the node and its
parent chain. Gating one config and not the others would skew the
comparison.

Phases, per the Jul 14 directive:
  Phase 0  --stub      wiring check, no API key, scripted agent, fake repo
  Phase 1  live        real LLM + local clone at base_commit
  Phase 2  Docker      swebench harness, % Resolved, sweagent CLI reference

Run (PowerShell):
  python exec_harness.py --stub --config structured_plan
  python exec_harness.py --config structured_plan --provider anthropic ^
      --repo-dir C:\\work\\astropy --instance-json <path> --plan-file <path>

TODO(pilot) markers give the build order, same convention as
pilot_swebench_spine.py.
"""

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone

OUT_DIR = "outputs"
MAX_TURNS = 30            # our cap, not a benchmark standard
MAX_OBS_CHARS = 3000
TEMPERATURE = 0
SCHEMA_VERSION = "exec_record/1"

DEFAULT_MODEL = {
    "google": "gemini-3.5-flash",       # banked runs, kept reproducible
    "anthropic": "claude-sonnet-4-6",
    # same tier as Sonnet (balanced), per the Jul 29 check.
    # TODO(pilot) 7: at wiring time check the OpenAI docs that this id is
    # live and that it takes temperature=0 - the GPT-5 reasoning family has
    # rejected the parameter before. If it isn't settable, note it in the
    # run provenance as a disclosed asymmetry rather than dropping it.
    "openai": "gpt-5.6-terra",
}

CONFIGS = ["noplan", "unstructured_plan", "trajectory_plan", "structured_plan"]

# actions a gate would veto - recorded, never blocked (see docstring)
GATE_PATTERNS = ["commit", "push", "pull request", "pull_request", "pr "]


# --- plan loading ----------------------------------------------------------
# Each config reads its own artifact type and the plan goes into the prompt
# verbatim: structured = the JSON tree, trajectory = parsed steps or raw
# text, unstructured = the prose.

def load_plan(config, plan_file):
    if config == "noplan":
        return None, "no plan (baseline)"
    if not plan_file:
        sys.exit("%s needs --plan-file" % config)
    data = json.load(open(plan_file, encoding="utf-8"))
    if config == "structured_plan":
        # pilot tree artifact: {"policies": [...]}
        tree = data if "policies" in data else json.loads(data["response_text"])
        return tree, "%d policies" % len(tree["policies"])
    if config == "trajectory_plan":
        steps = data.get("parsed_steps")
        if steps is None:
            # Claude's run 1 never parsed, so the raw text is the artifact
            return data["response_text"], "raw text (parse failed, disclosed)"
        return steps, "%d steps" % len(steps)
    if config == "unstructured_plan":
        return data["response_text"], "%d chars prose" % len(data["response_text"])
    sys.exit("unknown config %s" % config)


def build_prompt(config, plan, repo_dir, intent):
    base = (
        "You are a software engineering agent working in a repository at %s. "
        "Fix the following issue using the tools. When the fix is applied, "
        "call done with a one-line summary.\n\nISSUE:\n%s" % (repo_dir, intent)
    )
    if config == "noplan":
        return base
    plan_text = json.dumps(plan, indent=2) if isinstance(plan, (dict, list)) else plan
    extra = ""
    if config == "structured_plan":
        extra = ("\nOn EVERY tool call, state which policy id you are "
                 "executing by prefixing your reasoning with [P<id>].")
        # TODO(pilot) 3: pull the [P<id>] prefix off the AI message and write
        # it into policy_id at emit time.
    return base + "\n\nPLAN (follow it; deviate only with stated reason):\n" + plan_text + extra


# --- record schema, identical in every config ------------------------------

def make_record(step_id, action, observation, policy_id, config):
    gate_flag = any(p in json.dumps(action).lower() for p in GATE_PATTERNS)
    return {
        "schema_version": SCHEMA_VERSION,
        "step_id": step_id,
        "action": action,
        "observation": (observation or "")[:MAX_OBS_CHARS],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "policy_id": policy_id,          # only set in structured_plan
        "provenance_mode": ("recorded" if config == "structured_plan"
                            else "reconstructed"),
        "gate_flag": gate_flag,
    }


# --- tools -----------------------------------------------------------------
# Same four as the banked exec run, left unchanged so the noplan baseline
# stays comparable. TODO(pilot) 5: import these from the banked script
# instead of duplicating them.

def make_tools(repo_dir):
    def search_repo(term: str) -> str:
        """Search all Python files for a term."""
        return "stub hit: %s found in astropy/modeling/separable.py" % term

    def open_file(path: str, start: int = 1, end: int = 80) -> str:
        """Read lines start..end of a file."""
        return "stub contents of %s lines %d-%d" % (path, start, end)

    def edit_file(path: str, old: str, new: str) -> str:
        """Replace first occurrence of old with new."""
        return "stub edit applied to %s" % path

    def done(summary: str) -> str:
        """Call once when the fix is complete."""
        return "submitted: %s" % summary
    return [search_repo, open_file, edit_file, done]


# --- LangGraph action graph ------------------------------------------------
# Same shape for all four configs; only the plan slot in the state differs.
#
#   inject_plan -> agent_turn -> emit_record -> budget_gate -+-> agent_turn
#                                                            +-> finish
#
# inject_plan writes whatever load_plan returned (None / prose / trajectory
# steps / policy tree) into the state unchanged. Only build_prompt and the
# attribution parse care which representation it is.

from typing import TypedDict, Optional, Any, List


class AgentState(TypedDict):
    config: str
    intent: str
    plan: Any                 # None | prose str | trajectory steps | tree
    plan_desc: str
    prompt: str
    turn: int
    pending: Optional[dict]   # thought+action waiting on its observation
    records: List[dict]
    outcome: str


def build_graph(tools, agent_fn):
    """Compile the execute-arm graph.

    agent_fn(state) -> (thought, action_name, args) | None is the seam
    between stub and live: the stub passes a scripted function, live passes
    the LLM turn (TODO(pilot) 1). Returns a
    langgraph.graph.state.CompiledStateGraph, type-checked below under
    --stub as in the banked exec script.
    """
    from langgraph.graph import StateGraph, END
    tmap = {f.__name__: f for f in tools}

    def inject_plan(state: AgentState):
        # placeholder - the plan artifact goes into the state verbatim.
        # TODO(pilot) 6: for structured_plan, index the tree by id too, so
        # the attribution parse can check [P<id>] against real nodes.
        prompt = build_prompt(state["config"], state["plan"],
                              "stub_repo", state["intent"])
        return {"prompt": prompt, "turn": 0, "records": [],
                "outcome": "running", "pending": None}

    def agent_turn(state: AgentState):
        step = agent_fn(state)
        if step is None:
            return {"outcome": "agent_stopped"}
        thought, name, args = step
        obs = tmap[name](**args)
        return {"pending": {"thought": thought,
                            "action": {"name": name, "args": args},
                            "observation": obs}}

    def emit_record(state: AgentState):
        p = state["pending"]
        if p is None:
            return {}
        pid = None
        if state["config"] == "structured_plan" and \
                p["thought"].startswith("[P"):
            pid = p["thought"].split("]")[0].strip("[")
        rec = make_record(state["turn"],
                          {**p["action"], "thought": p["thought"]},
                          p["observation"], pid, state["config"])
        done = p["action"]["name"] == "done"
        return {"records": state["records"] + [rec],
                "turn": state["turn"] + 1,
                "pending": None,
                "outcome": "done" if done else state["outcome"]}

    def budget_gate(state: AgentState):
        if state["outcome"] in ("done", "agent_stopped"):
            return "finish"
        if state["turn"] >= MAX_TURNS:
            return "exhausted"
        return "continue"

    def finish(state: AgentState):
        out = state["outcome"]
        return {"outcome": "budget_exhausted" if out == "running" else out}

    g = StateGraph(AgentState)
    g.add_node("inject_plan", inject_plan)
    g.add_node("agent_turn", agent_turn)
    g.add_node("emit_record", emit_record)
    g.add_node("finish", finish)
    g.set_entry_point("inject_plan")
    g.add_edge("inject_plan", "agent_turn")
    g.add_edge("agent_turn", "emit_record")
    g.add_conditional_edges("emit_record", budget_gate,
                            {"continue": "agent_turn",
                             "exhausted": "finish",
                             "finish": "finish"})
    g.add_edge("finish", END)
    return g.compile()


# --- phase 0 ---------------------------------------------------------------
# Scripted agent: exercises the loop, the records and the gate flag with no
# API key.

def run_stub(config, tools):
    script = [
        ("[P2.1] run the reproduction first" if config == "structured_plan"
         else "find the function", "search_repo", {"term": "separability_matrix"}),
        ("[P5] apply the fix" if config == "structured_plan"
         else "apply the fix", "edit_file",
         {"path": "astropy/modeling/separable.py", "old": "x", "new": "y"}),
        ("[P7.1] commit the change" if config == "structured_plan"
         else "commit the change", "edit_file",
         {"path": "commit", "old": "", "new": ""}),   # trips gate_flag
        ("done", "done", {"summary": "stub run"}),
    ]

    def scripted_agent(state):
        i = state["turn"]
        return script[i] if i < len(script) else None

    graph = build_graph(tools, scripted_agent)
    # type check, as in the banked exec script: records that the compiled
    # object is a LangGraph graph
    from langgraph.graph.state import CompiledStateGraph
    assert isinstance(graph, CompiledStateGraph), type(graph)
    final = graph.invoke({"config": config,
                          "intent": "stub intent",
                          "plan": ("stub plan" if config != "noplan" else None),
                          "plan_desc": "stub"})
    return final["records"], final["outcome"]


def run_live(config, prompt, provider, model, tools):
    # TODO(pilot) 1: LangChain v1 create_agent over the four tools, streaming
    # with live progress, GraphRecursionError kept as a result plus the
    # partial trajectory. Take the loop from the banked Gemini exec script -
    # it already has outcome tracking and budget handling.
    # Providers: ChatGoogleGenerativeAI / ChatAnthropic / ChatOpenAI (pip
    # install langchain-openai for the third). Check TODO(pilot) 7 in
    # DEFAULT_MODEL for the OpenAI temperature caveat before the first run.
    # TODO(pilot) 2: fold each streamed AI message + tool result into one
    # record via make_record, as run_stub does.
    # TODO(pilot) 4: outputs named exec_<config>_<instance>_<model>_run<n>.json
    sys.exit("live mode not wired yet; run --stub. Build order: TODO(pilot) 1-5.")


def behavior_stats(records, outcome):
    print("turns            : %d" % len(records))
    print("outcome          : %s" % outcome)
    print("gate_flags       : %d (recorded, never blocked)"
          % sum(1 for r in records if r["gate_flag"]))
    attributed = sum(1 for r in records if r["policy_id"])
    print("policy_id set    : %d/%d (attribution at emit time)"
          % (attributed, len(records)))
    print("provenance_mode  : %s" % records[0]["provenance_mode"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", choices=CONFIGS, required=True)
    ap.add_argument("--provider", choices=["google", "anthropic", "openai"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--repo-dir")
    ap.add_argument("--instance-json")
    ap.add_argument("--plan-file", help="the plan artifact for this config")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--stub", action="store_true")
    args = ap.parse_args()

    tools = make_tools(args.repo_dir or "stub_repo")

    if args.stub:
        plan, plan_desc = (None, "stub") if args.config == "noplan" else \
            (load_plan(args.config, args.plan_file) if args.plan_file
             else ("stub plan", "stub plan"))
        records, outcome = run_stub(args.config, tools)
    else:
        if not (args.provider and args.repo_dir and args.instance_json):
            sys.exit("live mode needs --provider --repo-dir --instance-json")
        instance = json.load(open(args.instance_json, encoding="utf-8"))
        plan, plan_desc = load_plan(args.config, args.plan_file)
        prompt = build_prompt(args.config, plan, args.repo_dir,
                              instance["problem_statement"])
        model = args.model or DEFAULT_MODEL[args.provider]
        records, outcome = run_live(args.config, prompt, args.provider,
                                    model, tools)

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "exec_%s_stub_run%d.json"
                       % (args.config, args.run))
    json.dump({"config": args.config, "outcome": outcome,
               "records": records}, open(out, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print("records -> %s" % out)
    behavior_stats(records, outcome)
    if args.stub:
        print("\nSTUB RUN: wiring check only. Nothing above is a result.")


if __name__ == "__main__":
    main()