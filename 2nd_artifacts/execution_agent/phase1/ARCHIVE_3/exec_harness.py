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
import hashlib
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
# Each config reads its own run-2 artifact type, strictly. The harness
# contains no parser of its own: the structured branch consumes parsed_tree
# exactly as reparse_artifacts.py left it, and aborts if it is absent. The
# planner coordinates (who authored the plan) are read from the artifact's
# own provider/model fields, never typed by hand.

EXPECTED_PLAN_SCHEMA = {
    "unstructured_plan": "plan_unstructured/",
    "trajectory_plan": "plan_trajectory/",
    "structured_plan": "plan_structured/",
}


def load_plan(config, plan_file):
    """Returns (plan, plan_desc, plan_meta)."""
    if config == "noplan":
        meta = {"planner_provider": None, "planner_model": None,
                "plan_file": None, "plan_sha256": None,
                "plan_schema_version": None, "plan_instance_id": None}
        return None, "no plan (baseline)", meta
    if not plan_file:
        sys.exit("%s needs --plan-file" % config)
    raw = open(plan_file, "rb").read()
    data = json.loads(raw.decode("utf-8"))
    for field in ("provider", "model", "instance_id", "schema_version"):
        if not data.get(field):
            sys.exit("plan artifact missing %r; planner coordinates must "
                     "come from the artifact, not the command line" % field)
    want = EXPECTED_PLAN_SCHEMA[config]
    if not data["schema_version"].startswith(want):
        sys.exit("config %s expects a %s* artifact, got %r; wrong plan "
                 "file for this cell" % (config, want, data["schema_version"]))
    meta = {"planner_provider": data["provider"],
            "planner_model": data["model"],
            "plan_file": os.path.abspath(plan_file),
            "plan_sha256": hashlib.sha256(raw).hexdigest(),
            "plan_schema_version": data["schema_version"],
            "plan_instance_id": data["instance_id"]}
    if config == "structured_plan":
        tree = data.get("parsed_tree")
        if data.get("parse_error") is not None or not tree:
            sys.exit("structured artifact has no clean parsed_tree "
                     "(parse_error=%r); fix the artifact with "
                     "reparse_artifacts.py, the harness will not re-parse"
                     % data.get("parse_error"))
        pols = tree.get("policies")
        if not pols:
            sys.exit("parsed_tree has no policies")
        return tree, "%d policies, root %s" % (
            len(pols), [p.get("id") for p in pols
                        if p.get("parent_id") is None]), meta
    if config == "trajectory_plan":
        steps = data.get("parsed_steps")
        if not steps:
            sys.exit("trajectory artifact has no parsed_steps; fix the "
                     "artifact with reparse_artifacts.py, the harness "
                     "will not re-parse")
        return steps, "%d steps" % len(steps), meta
    if config == "unstructured_plan":
        text = data.get("response_text")
        if not text:
            sys.exit("unstructured artifact has no response_text")
        return text, "%d chars prose" % len(text), meta
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
# Same four signatures as the banked exec run so the noplan baseline stays
# comparable. Live implementations operate on the checkout from
# setup_exec_repo.py. Contracts:
#   - every tool returns a string observation and never raises; errors come
#     back as observations so the agent can read them and adapt
#   - what the model sees is exactly what the record stores: truncation
#     happens at the tool, marked in the text, capped at MAX_OBS_CHARS
#   - paths are jailed to the repo checkout; .git is invisible
#   - file writes are byte-safe (utf-8, newlines preserved) so the captured
#     diff never contains line-ending noise

MAX_SEARCH_HITS = 50
MAX_OPEN_LINES = 400


def _truncate(text):
    if len(text) <= MAX_OBS_CHARS:
        return text
    return (text[:MAX_OBS_CHARS]
            + "\n[truncated at %d chars; narrow the request]"
            % MAX_OBS_CHARS)


def make_real_tools(repo_dir):
    root = os.path.realpath(repo_dir)

    def safe_path(path):
        full = os.path.realpath(os.path.join(root, path))
        if full != root and not full.startswith(root + os.sep):
            return None
        if ".git" in os.path.relpath(full, root).split(os.sep):
            return None
        return full

    def search_repo(term: str) -> str:
        """Search all Python files for a term (case-sensitive substring)."""
        try:
            hits = []
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = sorted(d for d in dirnames
                                     if d != ".git" and not d.startswith("."))
                for fn in sorted(filenames):
                    if not fn.endswith(".py"):
                        continue
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, root).replace(os.sep, "/")
                    try:
                        lines = open(full, "rb").read().decode(
                            "utf-8", errors="replace").splitlines()
                    except OSError:
                        continue
                    for i, line in enumerate(lines, 1):
                        if term in line:
                            hits.append("%s:%d: %s" % (rel, i, line.strip()))
                            if len(hits) >= MAX_SEARCH_HITS:
                                hits.append("[hit cap %d reached; refine "
                                            "the term]" % MAX_SEARCH_HITS)
                                return _truncate("\n".join(hits))
            if not hits:
                return "no hits for %r in *.py" % term
            return _truncate("\n".join(hits))
        except Exception as e:
            return "tool error: %s" % e

    def open_file(path: str, start: int = 1, end: int = 80) -> str:
        """Read lines start..end of a file."""
        try:
            full = safe_path(path)
            if full is None:
                return "refused: %r is outside the repository" % path
            if not os.path.isfile(full):
                return "no such file: %s" % path
            start = max(1, int(start))
            end = int(end)
            if end - start + 1 > MAX_OPEN_LINES:
                end = start + MAX_OPEN_LINES - 1
            lines = open(full, "rb").read().decode(
                "utf-8", errors="replace").splitlines()
            if start > len(lines):
                return "%s has %d lines; start=%d is past the end" % (
                    path, len(lines), start)
            body = "\n".join("%6d| %s" % (n, lines[n - 1])
                             for n in range(start, min(end, len(lines)) + 1))
            return _truncate("%s lines %d-%d of %d\n%s" % (
                path, start, min(end, len(lines)), len(lines), body))
        except Exception as e:
            return "tool error: %s" % e

    def edit_file(path: str, old: str, new: str) -> str:
        """Replace first occurrence of old with new."""
        try:
            full = safe_path(path)
            if full is None:
                return "refused: %r is outside the repository" % path
            if not os.path.isfile(full):
                return "no such file: %s" % path
            if not old:
                return "refused: old must be non-empty"
            raw = open(full, "rb").read()
            text = raw.decode("utf-8")
            count = text.count(old)
            if count == 0:
                return "old string not found in %s (0 occurrences)" % path
            idx = text.index(old)
            line_no = text.count("\n", 0, idx) + 1
            updated = text.replace(old, new, 1)
            open(full, "wb").write(updated.encode("utf-8"))
            note = "" if count == 1 else \
                " (%d occurrences existed; only the first was replaced)" % count
            return "edit applied to %s at line %d%s" % (path, line_no, note)
        except Exception as e:
            return "tool error: %s" % e

    def done(summary: str) -> str:
        """Call once when the fix is complete."""
        return "submitted: %s" % summary

    return [search_repo, open_file, edit_file, done]


def make_stub_tools():
    # wiring-check fixtures only; kept so --stub needs no checkout
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


def capture_patch(repo_dir):
    """git diff of the working tree after the run; this field is what the
    Docker evaluator consumes. Untracked files are listed, not diffed."""
    import subprocess

    def g(*a):
        p = subprocess.run(["git"] + list(a), cwd=repo_dir,
                           capture_output=True, text=True)
        return p.returncode, p.stdout

    rc, _ = g("rev-parse", "--git-dir")
    if rc != 0:
        return {"model_patch": None,
                "note": "%s is not a git checkout; no patch captured"
                        % repo_dir}
    _, diff = g("diff", "HEAD")
    _, untracked = g("ls-files", "--others", "--exclude-standard")
    _, head = g("rev-parse", "HEAD")
    return {"model_patch": diff,
            "base_commit_at_capture": head.strip(),
            "untracked_files": untracked.split() if untracked.strip() else [],
            "edited": bool(diff.strip())}


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


def tool_check(repo_dir):
    """Exercise the real tools against the checkout with zero API calls.
    Makes one marker edit, verifies capture_patch sees it, reverses the
    edit, and verifies the tree is clean again."""
    search_repo, open_file, edit_file, _done = make_real_tools(repo_dir)
    print("[1] search_repo('separability_matrix')")
    hits = search_repo("separability_matrix")
    print(hits[:600])
    print("[2] open_file first hit region")
    first = hits.splitlines()[0]
    path, line = first.split(":")[0], int(first.split(":")[1])
    print(open_file(path, max(1, line - 2), line + 2))
    print("[3] jail checks")
    print("  " + open_file("../outside.txt"))
    print("  " + open_file(".git/config"))
    print("[4] edit_file miss")
    print("  " + edit_file(path, "STRING_THAT_DOES_NOT_EXIST", "x"))
    print("[5] marker edit + capture + revert")
    marker = "# tool_check marker\n"
    line1 = open(os.path.join(repo_dir, path), "rb").read() \
        .decode("utf-8").splitlines()[0] + "\n"
    obs = edit_file(path, line1, marker + line1)
    print("  " + obs)
    if not obs.startswith("edit applied"):
        sys.exit("tool check FAILED: the marker edit did not apply "
                 "(%r). If this mentions 0 occurrences, the working tree "
                 "likely has CRLF line endings; run setup_exec_repo.py "
                 "--reset and retry" % obs)
    cap = capture_patch(repo_dir)
    print("  capture sees edit : %s (%d diff chars)"
          % (cap.get("edited"), len(cap.get("model_patch") or "")))
    if not cap.get("edited"):
        sys.exit("tool check FAILED: the edit applied but capture_patch "
                 "did not see it")
    obs = edit_file(path, marker, "")
    print("  " + obs)
    if not obs.startswith("edit applied"):
        sys.exit("tool check FAILED: the reversal did not apply (%r); "
                 "run setup_exec_repo.py --reset to restore the tree" % obs)
    cap = capture_patch(repo_dir)
    print("  tree clean again  : %s" % (not cap.get("edited")))
    if cap.get("edited"):
        sys.exit("tool_check left the tree dirty; run setup_exec_repo.py "
                 "--reset before anything else")
    print("tool check passed; tools are live-ready")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", choices=CONFIGS)
    ap.add_argument("--provider", choices=["google", "anthropic", "openai"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--repo-dir")
    ap.add_argument("--instance-json")
    ap.add_argument("--plan-file", help="the plan artifact for this config")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--tool-check", action="store_true",
                    help="exercise the real tools, no API calls, tree left clean")
    args = ap.parse_args()

    if args.tool_check:
        if not args.repo_dir:
            sys.exit("--tool-check needs --repo-dir")
        tool_check(args.repo_dir)
        return
    if not args.config:
        sys.exit("--config is required (or use --tool-check)")

    tools = make_stub_tools() if args.stub else make_real_tools(args.repo_dir)

    if args.stub:
        if args.config == "noplan" or not args.plan_file:
            plan, plan_desc, plan_meta = load_plan("noplan", None)
            if args.config != "noplan":
                plan, plan_desc = "stub plan", "stub plan"
        else:
            plan, plan_desc, plan_meta = load_plan(args.config,
                                                   args.plan_file)
            print("plan loaded     : %s" % plan_desc)
            print("planner         : %s / %s"
                  % (plan_meta["planner_provider"],
                     plan_meta["planner_model"]))
            print("plan sha256     : %s" % plan_meta["plan_sha256"])
        records, outcome = run_stub(args.config, tools)
    else:
        if not (args.provider and args.repo_dir and args.instance_json):
            sys.exit("live mode needs --provider --repo-dir --instance-json")
        instance = json.load(open(args.instance_json, encoding="utf-8"))
        plan, plan_desc, plan_meta = load_plan(args.config, args.plan_file)
        if (plan_meta["plan_instance_id"] is not None
                and plan_meta["plan_instance_id"] != instance["instance_id"]):
            sys.exit("plan artifact is for %r but the instance is %r; "
                     "refusing to inject a plan for a different issue"
                     % (plan_meta["plan_instance_id"],
                        instance["instance_id"]))
        prompt = build_prompt(args.config, plan, args.repo_dir,
                              instance["problem_statement"])
        model = args.model or DEFAULT_MODEL[args.provider]
        records, outcome = run_live(args.config, prompt, args.provider,
                                    model, tools)

    patch = None if args.stub else capture_patch(args.repo_dir)
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "exec_%s_stub_run%d.json"
                       % (args.config, args.run))
    json.dump({"config": args.config, "outcome": outcome,
               "plan_meta": plan_meta, "plan_desc": plan_desc,
               "model_patch_capture": patch,
               "records": records}, open(out, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print("records -> %s" % out)
    behavior_stats(records, outcome)
    if args.stub:
        print("\nSTUB RUN: wiring check only. Nothing above is a result.")


if __name__ == "__main__":
    main()