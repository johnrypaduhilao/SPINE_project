"""
dispatch_harness.py

Structured dispatch, the recorded side run live. The policy tree is fed
to the agent one policy at a time; the harness stamps every record with
the id and action of the policy active at the moment of the call. IDs
are never asked from the model anywhere: the model's only protocol duty
is to call policy_complete when the current policy's action is done (or
impossible with the available tools), and the next policy arrives in
that tool's observation. Mis-timing therefore remains possible and is
recorded; mislabeling is impossible by construction.

Companion to exec_harness.py (must sit in the same directory; the base
contract text, plan loading gates, tools, model factory, and patch
capture are imported from it so the two harnesses cannot drift apart).
The contrast cell is the no-tag structured run of exec_harness.py: same
plan whole-in-context there, one-policy-at-a-time here.

Two rulings are implemented as proposed, formal ratification pending:
  - completion is signaled by the model via the policy_complete tool
  - dispatch scope is chosen per run via --dispatch-scope, required,
    no default: "full" dispatches every policy in artifact order,
    "imperatives" dispatches only level == "imperative" policies in
    artifact order

Run (PowerShell):
  python dispatch_harness.py --stub --dispatch-scope imperatives --plan-file <path>
  python dispatch_harness.py --dispatch-scope imperatives --provider anthropic ^
      --repo-dir <checkout> --instance-json <path> --plan-file <path> ^
      --account school --run 1 --dry-run
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

from exec_harness import (build_prompt, load_plan, make_real_tools,
                          make_stub_tools, make_exec_llm, capture_patch,
                          _msg_text, GATE_PATTERNS, MAX_OBS_CHARS,
                          MAX_TURNS, MAX_TOKENS, TEMPERATURE)

OUT_DIR = "outputs"
RECORD_SCHEMA = "exec_record/2"
RUN_SCHEMA = "exec_dispatch_run/1"
CONFIG = "structured_dispatch"


def build_queue(tree, scope):
    pols = tree["policies"]
    if scope == "full":
        q = list(pols)
    elif scope == "imperatives":
        q = [p for p in pols if p.get("level") == "imperative"]
    else:
        sys.exit("unknown dispatch scope %r" % scope)
    if not q:
        sys.exit("dispatch queue is empty under scope %r" % scope)
    return q


def policy_text(policy, k, n):
    return "CURRENT POLICY (%d of %d):\n%s" % (k, n,
                                               json.dumps(policy, indent=2))


PROTOCOL = (
    "\n\nPLAN PROTOCOL:\nThe plan for this issue is provided one policy "
    "at a time. Work on the current policy with the tools. When the "
    "current policy's action is complete, or cannot be performed with "
    "the available tools, call policy_complete with a one-line summary "
    "and the next policy will be provided.\n\n"
)


def build_initial_prompt(intent, queue):
    # base contract byte-identical to every exec_harness cell
    base = build_prompt("noplan", None, intent)
    return base + PROTOCOL + policy_text(queue[0], 1, len(queue))


def make_dispatch_record(step_id, action, observation, policy, config):
    gate_flag = any(p in json.dumps(action).lower() for p in GATE_PATTERNS)
    return {
        "schema_version": RECORD_SCHEMA,
        "step_id": step_id,
        "action": action,
        "observation": (observation or "")[:MAX_OBS_CHARS],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "policy_id": policy["id"] if policy else None,
        "policy_action": policy["action"] if policy else None,
        "provenance_mode": "recorded" if policy else "reconstructed",
        "gate_flag": gate_flag,
    }


def run_dispatch(prompt, queue, provider, model, tools_base):
    """The live loop. Mirrors exec_harness.run_live turn for turn, with
    two additions: the policy_complete tool that advances the queue, and
    system stamping of the active policy on every emitted record."""
    from langchain_core.messages import HumanMessage, ToolMessage
    from langchain_core.tools import tool as lc_tool

    disp = {"queue": queue, "idx": 0, "transitions": [
        {"policy_id": queue[0]["id"], "activated_turn": 0,
         "completed_turn": None, "completion_summary": None}]}

    def active():
        return disp["queue"][disp["idx"]] if disp["idx"] < len(disp["queue"]) else None

    def policy_complete(summary: str) -> str:
        """Call when the current policy is complete or impossible."""
        cur = active()
        if cur is None:
            return ("no active policy; all policies were already "
                    "dispatched. When the fix is applied, call done "
                    "with a one-line summary.")
        disp["transitions"][-1]["completion_summary"] = summary
        disp["idx"] += 1
        nxt = active()
        if nxt is None:
            return ("recorded. All policies dispatched. When the fix is "
                    "applied, call done with a one-line summary.")
        return "recorded. " + policy_text(nxt, disp["idx"] + 1,
                                          len(disp["queue"]))

    tools = tools_base + [policy_complete]
    tmap = {f.__name__: f for f in tools}

    def bind(llm):
        lc_tools = [lc_tool(f) for f in tools]
        try:
            return llm.bind_tools(lc_tools, parallel_tool_calls=False)
        except TypeError:
            return llm.bind_tools(lc_tools)

    raw_llm = make_exec_llm(provider, model)
    box = {"llm": bind(raw_llm), "messages": [HumanMessage(prompt)],
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

    records = []
    outcome = "running"
    t0 = time.perf_counter()
    while outcome == "running":
        if len(records) >= MAX_TURNS:
            outcome = "budget_exhausted"
            break
        if box["last_call_id"] is not None and records:
            box["messages"].append(ToolMessage(
                content=records[-1]["observation"],
                tool_call_id=box["last_call_id"]))
            box["last_call_id"] = None
        print("turn %d " % len(records), end="", flush=True)
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
                    outcome = "agent_stopped"
                    break
            else:
                box["error"] = str(e)
                outcome = "agent_stopped"
                break
        if ai is None:
            box["error"] = "empty stream"
            outcome = "agent_stopped"
            break
        calls = getattr(ai, "tool_calls", None) or []
        thought = _msg_text(ai.content)
        if not calls:
            box["final_text"] = thought
            outcome = "agent_stopped"
            break
        box["messages"].append(ai)
        tc = calls[0]
        box["last_call_id"] = tc.get("id")
        for extra in calls[1:]:
            box["messages"].append(ToolMessage(
                content="not executed: one tool call per turn; resubmit "
                        "this call on a later turn if still needed",
                tool_call_id=extra.get("id")))
        # the stamp: the policy active at the moment of the call. A
        # policy_complete turn belongs to the policy it closes, so the
        # stamp is taken before the tool advances the queue.
        stamp = active()
        try:
            obs = tmap[tc["name"]](**(tc.get("args") or {}))
        except KeyError:
            obs = "tool error: no tool named %r" % tc["name"]
        except TypeError as e:
            obs = "tool error: bad arguments for %s: %s" % (tc["name"], e)
        rec = make_dispatch_record(
            len(records),
            {"name": tc["name"], "args": tc.get("args") or {},
             "thought": thought},
            obs, stamp, CONFIG)
        usage = getattr(ai, "usage_metadata", None) or {}
        if usage:
            rec["usage"] = usage
        rec["wall_s"] = round(wall, 2)
        if len(calls) > 1:
            rec["parallel_calls_dropped"] = len(calls) - 1
        records.append(rec)
        if (tc["name"] == "policy_complete" and stamp is not None
                and active() is not None
                and disp["transitions"][-1]["policy_id"] != active()["id"]):
            disp["transitions"][-1]["completed_turn"] = rec["step_id"]
            disp["transitions"].append(
                {"policy_id": active()["id"],
                 "activated_turn": rec["step_id"] + 1,
                 "completed_turn": None, "completion_summary": None})
        elif (tc["name"] == "policy_complete" and stamp is not None
                and active() is None):
            disp["transitions"][-1]["completed_turn"] = rec["step_id"]
        if tc["name"] == "done":
            outcome = "done"
    remaining = [p["id"] for p in disp["queue"][disp["idx"]:]]
    extra = {"temperature_dropped": box["dropped"],
             "temperature_effective": box["temperature_effective"],
             "final_text": box["final_text"],
             "stream_error": box["error"],
             "wall_s_total": round(time.perf_counter() - t0, 2),
             "transitions": disp["transitions"],
             "remaining_policies": remaining}
    return records, outcome, extra


def run_stub(queue):
    """Wiring check, no API: work, complete, work, complete, done."""
    outs = []

    script = [
        ("look around", "search_repo", {"term": "separability_matrix"}),
        ("first policy is done", "policy_complete", {"summary": "did it"}),
        ("apply the fix", "edit_file",
         {"path": "astropy/modeling/separable.py", "old": "x", "new": "y"}),
        ("second policy is done", "policy_complete", {"summary": "done 2"}),
        ("finish", "done", {"summary": "stub"}),
    ]
    idx = {"i": 0}
    stubs = {f.__name__: f for f in make_stub_tools()}

    for step_id, (thought, name, args) in enumerate(script):
        stamp = queue[idx["i"]] if idx["i"] < len(queue) else None
        if name == "policy_complete":
            obs = "stub advance"
            idx["i"] += 1
        elif name in stubs:
            obs = stubs[name](**args)
        else:
            obs = "tool error"
        rec = make_dispatch_record(step_id,
                                   {"name": name, "args": args,
                                    "thought": thought}, obs, stamp, CONFIG)
        outs.append(rec)
    return outs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dispatch-scope", choices=["full", "imperatives"],
                    required=True,
                    help="which policies are dispatched, in artifact "
                         "order; ruling pending, so no default")
    ap.add_argument("--provider", choices=["google", "anthropic", "openai"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--repo-dir")
    ap.add_argument("--instance-json")
    ap.add_argument("--plan-file", required=True)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--account", default=None)
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    tree, plan_desc, plan_meta = load_plan("structured_plan",
                                           args.plan_file)
    queue = build_queue(tree, args.dispatch_scope)
    # instrument text must never truncate silently: every injection
    # (the policy_complete observation carrying the next policy) has to
    # fit inside the observation cap, or the run must not start
    for i, p in enumerate(queue):
        inj = "recorded. " + policy_text(p, i + 1, len(queue))
        if len(inj) > MAX_OBS_CHARS:
            sys.exit("policy %s injection is %d chars, over the %d "
                     "observation cap; it would be silently cut. Raise "
                     "MAX_OBS_CHARS in exec_harness or shorten the "
                     "policy before any live call"
                     % (p["id"], len(inj), MAX_OBS_CHARS))

    if args.stub:
        records = run_stub(queue)
        print("stub records:")
        for r in records:
            print("  t%02d %-16s policy_id=%-6r policy_action=%-10r mode=%s"
                  % (r["step_id"], r["action"]["name"], r["policy_id"],
                     r["policy_action"], r["provenance_mode"]))
        print("\nSTUB RUN: wiring check only. Nothing above is a result.")
        return

    if not (args.provider and args.repo_dir and args.instance_json):
        sys.exit("live mode needs --provider --repo-dir --instance-json")
    instance = json.load(open(args.instance_json, encoding="utf-8"))
    if (plan_meta["plan_instance_id"] is not None
            and plan_meta["plan_instance_id"] != instance["instance_id"]):
        sys.exit("plan artifact is for %r but the instance is %r"
                 % (plan_meta["plan_instance_id"], instance["instance_id"]))
    prompt = build_initial_prompt(instance["problem_statement"], queue)
    model = args.model or {"anthropic": "claude-sonnet-4-6",
                           "openai": "gpt-5.6-terra"}.get(args.provider) \
        or sys.exit("no default model for provider %r" % args.provider)
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    injections = [policy_text(p, i + 1, len(queue))
                  for i, p in enumerate(queue)]
    manifest_sha = hashlib.sha256(
        "\n".join(injections).encode("utf-8")).hexdigest()
    print("config          : %s" % CONFIG)
    print("dispatch scope  : %s" % args.dispatch_scope)
    print("instance        : %s" % instance["instance_id"])
    print("plan            : %s" % plan_desc)
    print("queue           : %s" % [p["id"] for p in queue])
    print("planner         : %s / %s" % (plan_meta["planner_provider"],
                                         plan_meta["planner_model"]))
    print("executor        : %s / %s" % (args.provider, model))
    print("initial sha256  : %s" % prompt_sha)
    print("initial chars   : %d" % len(prompt))
    print("manifest sha256 : %s" % manifest_sha)
    if args.dry_run:
        print("\nDRY RUN: no call made. Nothing below is a result.")
        print("-" * 72)
        print(prompt)
        print("-" * 72)
        return

    tools_base = make_real_tools(args.repo_dir)
    records, outcome, extra = run_dispatch(prompt, queue, args.provider,
                                           model, tools_base)
    patch = capture_patch(args.repo_dir)
    usage_total = {}
    for r in records:
        for k, v in (r.get("usage") or {}).items():
            if isinstance(v, int):
                usage_total[k] = usage_total.get(k, 0) + v
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR,
                       "exec_dispatch_%s_planner-%s_executor-%s_scope-%s_run%d.json"
                       % (instance["instance_id"],
                          plan_meta["planner_model"] or "none",
                          model, args.dispatch_scope, args.run))
    if os.path.exists(out):
        sys.exit("refusing to overwrite existing artifact %s; bump --run "
                 "or move the file first" % out)
    json.dump({
        "schema_version": RUN_SCHEMA,
        "config": CONFIG,
        "dispatch_scope": args.dispatch_scope,
        "policy_queue": [p["id"] for p in queue],
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
        "api_account": args.account,
        "outcome": outcome,
        "stream_error": extra["stream_error"],
        "final_text": extra["final_text"],
        "initial_prompt_sha256": prompt_sha,
        "dispatch_manifest_sha256": manifest_sha,
        "initial_prompt": prompt,
        "policy_transitions": extra["transitions"],
        "remaining_policies": extra["remaining_policies"],
        "wall_s_total": extra["wall_s_total"],
        "usage_total": usage_total,
        "model_patch_capture": patch,
        "records": records,
    }, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("dispatch run -> %s" % out)
    print("turns            : %d" % len(records))
    print("outcome          : %s" % outcome)
    stamped = sum(1 for r in records if r["policy_id"])
    print("policy_id set    : %d/%d (system-stamped)" % (stamped, len(records)))
    print("remaining        : %s" % extra["remaining_policies"])
    print("edited           : %s" % patch.get("edited"))
    print("usage total      : %s" % json.dumps(usage_total))
    if extra["stream_error"]:
        print("stream error     : %s" % extra["stream_error"])


if __name__ == "__main__":
    main()
