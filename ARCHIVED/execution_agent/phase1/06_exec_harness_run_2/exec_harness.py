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
import re
import os
import shutil
import sys
import time
from datetime import datetime, timezone

OUT_DIR = "outputs"
MAX_TURNS = 30            # our cap, not a benchmark standard
MAX_OBS_CHARS = 3000
TEMPERATURE = 0
MAX_TOKENS = 16000        # raised from 8000: reasoning-tier models spend
                          # hidden tokens inside the completion budget
SCHEMA_VERSION = "exec_record/2"

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


def build_prompt(config, plan, intent, tail="v1"):
    base = (
        "You are a software engineering agent working in a repository. "
        "Use the tools to inspect and modify the code; paths are relative "
        "to the repository root. Fix the following issue. When the fix is "
        "applied, call done with a one-line summary.\n\nISSUE:\n%s" % intent
    )
    if config == "noplan":
        return base
    plan_text = json.dumps(plan, indent=2) if isinstance(plan, (dict, list)) else plan
    extra = ""
    if config == "structured_plan":
        if tail == "v6":
            extra = (
                "\nThese tags exist for audit and traceability. Every "
                "record of this run is stored together with the policy id "
                "you cite, and an auditor later uses those ids to trace "
                "each action back through the plan to the original intent. "
                "An action recorded with a missing or wrong id cannot be "
                "traced."
                "\nOn every tool call, include two tags in your reasoning:"
                "\n- <policy_id>ID</policy_id> where ID is the \"id\" field "
                "of the one policy in the plan above whose action this "
                "tool call performs."
                "\n- <policy_action>ACTION</policy_action> where ACTION is "
                "that policy's \"action\" field, copied exactly."
                "\nAlways cite the most specific applicable policy, the "
                "deepest matching policy rather than its parent."
                "\nIf a policy cannot be performed with the available "
                "tools, state this explicitly in your reasoning and cite "
                "that policy's id in the same <policy_id> form."
                "\nBefore calling done, you must account for every policy "
                "you have not cited. For each such policy, state its id "
                "and whether it was: completed, subsumed by a cited "
                "policy, or impossible with the available tools.")
            return (base + "\n\nPLAN (follow it; deviate only with stated "
                    "reason):\n" + plan_text + extra)
        if tail == "v5":
            extra = (
                "\nOn every tool call, include two tags in your reasoning:"
                "\n- <policy_id>ID</policy_id> where ID is the \"id\" field "
                "of the one policy in the plan above whose action this "
                "tool call performs."
                "\n- <policy_action>ACTION</policy_action> where ACTION is "
                "that policy's \"action\" field, copied exactly."
                "\nAlways cite the most specific applicable policy, the "
                "deepest matching policy rather than its parent."
                "\nIf a policy cannot be performed with the available "
                "tools, state this explicitly in your reasoning and cite "
                "that policy's id in the same <policy_id> form."
                "\nBefore calling done, you must account for every policy "
                "you have not cited. For each such policy, state its id "
                "and whether it was: completed, subsumed by a cited "
                "policy, or impossible with the available tools.")
            return (base + "\n\nPLAN (follow it; deviate only with stated "
                    "reason):\n" + plan_text + extra)
        if tail == "v4":
            extra = (
                "\nOn EVERY tool call, include two tags in your reasoning: "
                "<policy_id>ID</policy_id> where ID is the \"id\" field of "
                "the one policy in the plan above whose action this tool "
                "call performs, and <policy_action>ACTION</policy_action> "
                "where ACTION is that policy's \"action\" field copied "
                "exactly. If a policy cannot be performed with the "
                "available tools, state this in your reasoning, citing its "
                "id the same way. Before calling done, account for every "
                "policy you have not cited: for each, state its \"id\" and "
                "whether it was completed, subsumed by a cited policy, or "
                "impossible with the available tools.")
            return (base + "\n\nPLAN (follow it; deviate only with stated "
                    "reason):\n" + plan_text + extra)
        extra = ("\nOn EVERY tool call, state which policy id you are "
                 "executing by prefixing your reasoning with [P<id>].")
        if tail in ("v2", "v3"):
            extra += (
                " The <id> is the \"id\" field of exactly one policy in the "
                "plan above, never its \"parent_id\". Cite the most specific "
                "policy whose action the tool call performs, the deepest "
                "matching policy rather than an ancestor. If a policy cannot "
                "be performed with the available tools, state this "
                "explicitly in your reasoning, citing that policy's \"id\" "
                "in the same [P<id>] form.")
        if tail == "v3":
            extra += (
                " The cited id must name the policy whose action the tool "
                "call itself performs, even if your reasoning at that "
                "moment serves a different policy. Before calling done, "
                "account for every policy you have not cited: for each, "
                "state its \"id\" and whether it was completed, subsumed by "
                "a cited policy, or impossible with the available tools.")
    return base + "\n\nPLAN (follow it; deviate only with stated reason):\n" + plan_text + extra


# --- record schema, identical in every config ------------------------------

def make_record(step_id, action, observation, policy_id, config,
                usage=None, wall_s=None, parallel_calls_dropped=0):
    gate_flag = any(p in json.dumps(action).lower() for p in GATE_PATTERNS)
    rec = {
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
    if usage:
        rec["usage"] = usage
    if wall_s is not None:
        rec["wall_s"] = wall_s
    if parallel_calls_dropped:
        rec["parallel_calls_dropped"] = parallel_calls_dropped
    return rec


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
    tail: str                 # structured-tail version; "v1" unless set
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
        # the prompt arrives fully built in the initial state; attribution
        # of [P<id>] against real tree nodes is the scorer's job
        return {"turn": 0, "records": [], "outcome": "running",
                "pending": None}

    def agent_turn(state: AgentState):
        step = agent_fn(state)
        if step is None:
            return {"outcome": "agent_stopped"}
        try:
            obs = tmap[step["name"]](**step["args"])
        except KeyError:
            obs = "tool error: no tool named %r" % step["name"]
        except TypeError as e:
            obs = "tool error: bad arguments for %s: %s" % (step["name"], e)
        return {"pending": {**step, "observation": obs}}

    def emit_record(state: AgentState):
        p = state["pending"]
        if p is None:
            return {}
        pid = None
        echo = None
        tail = state.get("tail", "v1")
        if state["config"] == "structured_plan":
            if tail in ("v4", "v5", "v6"):
                m = re.search(r"<policy_id>\s*(P[^<\s]*)\s*</policy_id>",
                              p["thought"] or "")
                if m:
                    pid = m.group(1)
                a = re.search(
                    r"<policy_action>\s*([^<]*?)\s*</policy_action>",
                    p["thought"] or "")
                if a:
                    echo = a.group(1)
            else:
                m = re.match(r"\s*\[(P[^\]\s]*)\]", p["thought"] or "")
                if m:
                    pid = m.group(1)
        rec = make_record(state["turn"],
                          {"name": p["name"], "args": p["args"],
                           "thought": p["thought"]},
                          p["observation"], pid, state["config"],
                          usage=p.get("usage"), wall_s=p.get("wall_s"),
                          parallel_calls_dropped=p.get(
                              "parallel_calls_dropped", 0))
        if state["config"] == "structured_plan" and tail in ("v4", "v5", "v6"):
            rec["policy_action_echo"] = echo
        done = p["name"] == "done"
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
        if i >= len(script):
            return None
        thought, name, args = script[i]
        return {"thought": thought, "name": name, "args": args}

    graph = build_graph(tools, scripted_agent)
    # type check, as in the banked exec script: records that the compiled
    # object is a LangGraph graph
    from langgraph.graph.state import CompiledStateGraph
    assert isinstance(graph, CompiledStateGraph), type(graph)
    final = graph.invoke({"config": config,
                          "tail": "v1",
                          "intent": "stub intent",
                          "plan": ("stub plan" if config != "noplan" else None),
                          "plan_desc": "stub", "prompt": "stub prompt"},
                         config={"recursion_limit": 2 * MAX_TURNS + 10})
    return final["records"], final["outcome"]


def make_exec_llm(provider, model, drop_temperature=False):
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, temperature=TEMPERATURE,
                             max_tokens=MAX_TOKENS)
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        # reasoning-tier models reject function tools on the chat
        # completions endpoint; the Responses API supports both. Transport
        # change only: temperature and max_tokens are unchanged and the
        # asymmetry is recorded in the artifact.
        kwargs = {"model": model, "max_tokens": MAX_TOKENS,
                  "use_responses_api": True}
        if not drop_temperature:
            kwargs["temperature"] = TEMPERATURE
        try:
            return ChatOpenAI(stream_usage=True, **kwargs)
        except TypeError as e:
            sys.exit("ChatOpenAI rejected an argument (%s); "
                     "pip install -U langchain-openai (use_responses_api "
                     "and stream_usage are required for the exec arm)" % e)
    sys.exit("unknown provider: %s (google is banked, not wired live)"
             % provider)


def _msg_text(content):
    if isinstance(content, str):
        return content
    return " ".join(b.get("text", "") for b in content
                    if isinstance(b, dict)).strip()


def run_live(config, prompt, provider, model, tools, tail="v1"):
    """One live exec run. The agent seam feeds each observation back as a
    ToolMessage before the next turn; every turn streams, meters its own
    usage, and lands in one record. Temperature rejection is retried once
    without it and recorded, mirroring the plan runners."""
    from langchain_core.messages import HumanMessage, ToolMessage
    from langchain_core.tools import tool as lc_tool

    def bind(llm):
        lc_tools = [lc_tool(f) for f in tools]
        try:
            return llm.bind_tools(lc_tools, parallel_tool_calls=False)
        except TypeError:
            return llm.bind_tools(lc_tools)

    raw_llm = make_exec_llm(provider, model)
    box = {"llm": bind(raw_llm),
           "messages": [HumanMessage(prompt)],
           "temperature_effective": getattr(raw_llm, "temperature", None),
           "last_call_id": None, "dropped": False,
           "final_text": None, "error": None}

    def stream_turn():
        final = None
        t0 = time.perf_counter()
        for chunk in box["llm"].stream(box["messages"]):
            final = chunk if final is None else final + chunk
            print(".", end="", flush=True)
        print()
        return final, time.perf_counter() - t0

    def agent_fn(gstate):
        if box["last_call_id"] is not None and gstate["records"]:
            box["messages"].append(ToolMessage(
                content=gstate["records"][-1]["observation"],
                tool_call_id=box["last_call_id"]))
            box["last_call_id"] = None
        print("turn %d " % gstate["turn"], end="", flush=True)
        try:
            ai, wall = stream_turn()
        except Exception as e:
            if (provider == "openai" and not box["dropped"]
                    and "temperature" in str(e).lower()):
                box["dropped"] = True
                print("temperature rejected; retrying without it",
                      flush=True)
                retry_llm = make_exec_llm(provider, model,
                                          drop_temperature=True)
                box["llm"] = bind(retry_llm)
                box["temperature_effective"] = getattr(
                    retry_llm, "temperature", None)
                try:
                    ai, wall = stream_turn()
                except Exception as e2:
                    box["error"] = str(e2)
                    return None
            else:
                box["error"] = str(e)
                return None
        if ai is None:
            box["error"] = "empty stream"
            return None
        calls = getattr(ai, "tool_calls", None) or []
        thought = _msg_text(ai.content)
        if not calls:
            box["final_text"] = thought
            return None
        box["messages"].append(ai)
        tc = calls[0]
        box["last_call_id"] = tc.get("id")
        return {"thought": thought, "name": tc["name"],
                "args": tc.get("args") or {},
                "usage": getattr(ai, "usage_metadata", None) or {},
                "wall_s": round(wall, 2),
                "parallel_calls_dropped": len(calls) - 1}

    graph = build_graph(tools, agent_fn)
    t0 = time.perf_counter()
    final = graph.invoke({"config": config, "tail": tail,
                          "intent": "", "plan": None,
                          "plan_desc": "", "prompt": prompt},
                         config={"recursion_limit": 2 * MAX_TURNS + 10})
    extra = {"temperature_dropped": box["dropped"],
             "temperature_effective": box["temperature_effective"],
             "final_text": box["final_text"],
             "stream_error": box["error"],
             "wall_s_total": round(time.perf_counter() - t0, 2)}
    return final["records"], final["outcome"], extra


def behavior_stats(records, outcome):
    print("turns            : %d" % len(records))
    print("outcome          : %s" % outcome)
    if not records:
        print("no records (agent produced no tool call)")
        return
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
    ap.add_argument("--tail", choices=["v1", "v2", "v3", "v4", "v5", "v6"], default="v1",
                    help="structured-tail version; v1 reproduces the "
                         "banked instrument byte-for-byte")
    ap.add_argument("--account", default=None,
                    help="API account label recorded in the artifact")
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="build and print the exact prompt + hashes, no call")
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
    if args.tail != "v1" and args.config != "structured_plan":
        sys.exit("--tail v2 only applies to structured_plan; the other "
                 "configs carry no tail and must not be labeled with one")

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
        prompt = build_prompt(args.config, plan,
                              instance["problem_statement"], args.tail)
        model = args.model or DEFAULT_MODEL[args.provider]
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        print("config          : %s" % args.config)
        if args.config == "structured_plan":
            print("instrument tail : %s" % args.tail)
        print("instance        : %s" % instance["instance_id"])
        print("plan            : %s" % plan_desc)
        print("planner         : %s / %s" % (plan_meta["planner_provider"],
                                             plan_meta["planner_model"]))
        print("executor        : %s / %s" % (args.provider, model))
        print("prompt sha256   : %s" % prompt_sha)
        print("prompt chars    : %d" % len(prompt))
        if args.dry_run:
            print("\nDRY RUN: no call made. Nothing below is a result.")
            print("-" * 72)
            print(prompt)
            print("-" * 72)
            return
        records, outcome, extra = run_live(args.config, prompt,
                                           args.provider, model, tools,
                                           tail=args.tail)

    if args.stub:
        patch = None
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
        print("\nSTUB RUN: wiring check only. Nothing above is a result.")
        return

    patch = capture_patch(args.repo_dir)
    usage_total = {}
    for r in records:
        for k, v in (r.get("usage") or {}).items():
            if isinstance(v, int):
                usage_total[k] = usage_total.get(k, 0) + v
    os.makedirs(OUT_DIR, exist_ok=True)
    tail_tag = ("_tail-%s" % args.tail
                if (args.config == "structured_plan" and args.tail != "v1")
                else "")
    out = os.path.join(OUT_DIR,
                       "exec_%s_%s_planner-%s_executor-%s%s_run%d.json"
                       % (args.config, instance["instance_id"],
                          plan_meta["planner_model"] or "none",
                          model, tail_tag, args.run))
    if os.path.exists(out):
        sys.exit("refusing to overwrite existing artifact %s; bump --run "
                 "or move the file first" % out)
    json.dump({
        "schema_version": "exec_run/1",
        "config": args.config,
        "instance_id": instance["instance_id"],
        "executor_provider": args.provider,
        "executor_model": model,
        "openai_use_responses_api": (True if args.provider == "openai"
                                     else None),
        "plan_meta": plan_meta,
        "plan_desc": plan_desc,
        "temperature": TEMPERATURE,
        "temperature_effective": extra["temperature_effective"],
        "temperature_dropped": extra["temperature_dropped"],
        "max_tokens": MAX_TOKENS,
        "max_turns": MAX_TURNS,
        "run": args.run,
        "instrument_tail": (args.tail if args.config == "structured_plan"
                            else None),
        "api_account": args.account,
        "outcome": outcome,
        "stream_error": extra["stream_error"],
        "final_text": extra["final_text"],
        "prompt_sha256": prompt_sha,
        "prompt": prompt,
        "wall_s_total": extra["wall_s_total"],
        "usage_total": usage_total,
        "model_patch_capture": patch,
        "records": records,
    }, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("exec run -> %s" % out)
    behavior_stats(records, outcome)
    print("edited          : %s" % patch.get("edited"))
    print("usage total     : %s" % json.dumps(usage_total))
    if extra["stream_error"]:
        print("stream error    : %s" % extra["stream_error"])


if __name__ == "__main__":
    main()