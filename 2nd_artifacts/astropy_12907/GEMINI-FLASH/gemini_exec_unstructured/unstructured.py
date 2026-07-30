"""
arm_a_unstructured.py

Arm A of the pilot: the UNSTRUCTURED baseline agent, built in LangGraph per
Dr. Nasim's July 10 request (same framework as Arm B; only the recording
differs). It runs a plain ReAct loop (LangGraph's prebuilt agent) over
simple repo tools and persists exactly what today's systems persist: a flat
trajectory of thought / action / observation. No tuples, no definer, no
parent pointers, by construction.

Phases (stepwise, per the July 14 directive):
  Phase 0  --stub          wiring check, no API key, tiny fake repo
  Phase 1  live, local     real LLM + a real local clone of the instance
                           repo at base_commit; produces a REAL flat
                           trajectory; tests NOT run yet (Docker phase)
  Phase 2  Docker          test execution + % Resolved (separate step)

Run (PowerShell):
  python arm_a_unstructured.py --stub
  python arm_a_unstructured.py --repo-dir C:\\work\\astropy --instance-json outputs\\astropy__astropy-12907.json

Live prerequisites:
  pip install langgraph langchain-google-genai
  set GOOGLE_API_KEY=...      (PowerShell: $env:GOOGLE_API_KEY="...")
  a local clone at the instance's base_commit:
    git clone --filter=blob:none https://github.com/astropy/astropy C:\\work\\astropy
    cd C:\\work\\astropy
    git checkout d16bfe05a744909de4b27f5875fe0d4ed41ce607

Behavior stats are printed after each run because the July 14 directive is
to UNDERSTAND the baseline's behavior before adding structure.
"""

import argparse
import json
import os
import shutil
import sys
import time

OUT_DIR = "outputs"
MODEL = "gemini-3.5-flash"    # temperature 0, project convention
MAX_TURNS = 30                # budget: loop stops here, run marked exhausted
MAX_OBS_CHARS = 3000          # every observation is truncated to this

STUB_INSTANCE = {
    "instance_id": "STUB__example-0001",
    "problem_statement": (
        "Division by zero crashes the calculator. Calling divide(1, 0) "
        "raises an unhandled ZeroDivisionError; it should raise a "
        "CalculatorError with a clear message instead."
    ),
}


# ---------------------------------------------------------------------------
# Tools: deliberately generic (search / open / edit / done), SWE-agent style.
# All outputs bounded so a huge repo cannot flood the context.
# ---------------------------------------------------------------------------

def make_tools(repo_dir):

    def _clip(s):
        s = str(s)
        return s if len(s) <= MAX_OBS_CHARS else s[:MAX_OBS_CHARS] + "...[truncated]"

    def search_repo(term: str) -> str:
        """Search all Python files for a term. Returns file:line hits (max 30)."""
        hits = []
        for root, _dirs, files in os.walk(repo_dir):
            if ".git" in root:
                continue
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                try:
                    for i, line in enumerate(open(path, errors="ignore"), 1):
                        if term in line:
                            rel = os.path.relpath(path, repo_dir)
                            hits.append("%s:%d: %s" % (rel, i, line.strip()[:120]))
                            if len(hits) >= 30:
                                return _clip("\n".join(hits) + "\n[stopped at 30 hits]")
                except OSError:
                    continue
        return _clip("\n".join(hits) if hits else "no hits for: %s" % term)

    def open_file(path: str, start: int = 1, end: int = 80) -> str:
        """Read lines start..end of a file (relative path). Max 120 lines."""
        full = os.path.join(repo_dir, path)
        if not os.path.isfile(full):
            return "no such file: %s" % path
        end = min(end, start + 119)
        lines = open(full, errors="ignore").readlines()
        chunk = lines[start - 1:end]
        out = "".join("%d\t%s" % (start + i, l) for i, l in enumerate(chunk))
        return _clip(out if out else "empty range")

    def edit_file(path: str, old: str, new: str) -> str:
        """Replace the first occurrence of old with new in the file."""
        full = os.path.join(repo_dir, path)
        if not os.path.isfile(full):
            return "no such file: %s" % path
        text = open(full, errors="ignore").read()
        if old not in text:
            return "anchor not found; open the file and copy the exact text"
        open(full, "w").write(text.replace(old, new, 1))
        return "edit applied to %s" % path

    def done(summary: str) -> str:
        """Call this once when the fix is complete, with a one-line summary."""
        return "submitted: %s" % summary

    return [search_repo, open_file, edit_file, done]


# ---------------------------------------------------------------------------
# Trajectory capture: the flat log, and nothing else. Thought text is
# whatever free text the model produced alongside each tool call.
# ---------------------------------------------------------------------------

def run_live(intent, repo_dir):
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain.agents import create_agent
    from langgraph.errors import GraphRecursionError

    tools = make_tools(repo_dir)
    agent = create_agent(ChatGoogleGenerativeAI(model=MODEL, temperature=0), tools)

    prompt = (
        "You are a software engineering agent working in a repository at %s. "
        "Fix the following issue using the tools. When the fix is applied, "
        "call done with a one-line summary.\n\nISSUE:\n%s" % (repo_dir, intent)
    )

    events = []
    pending = None
    t0 = time.perf_counter()

    # Stream instead of invoke: the loop is otherwise silent for many minutes
    # (one LLM round trip per turn), which is indistinguishable from a hang.
    # Each streamed message is folded into the flat trajectory as it arrives:
    # an AI message's free text is the thought and its tool calls the actions;
    # the following tool messages are the observations.
    print("running (%s, up to %d turns) ..." % (MODEL, MAX_TURNS), flush=True)
    outcome = "stopped"
    try:
        for chunk in agent.stream({"messages": [("user", prompt)]},
                                  config={"recursion_limit": MAX_TURNS * 2},
                                  stream_mode="updates"):
            for update in chunk.values():
                if not isinstance(update, dict):
                    continue
                for m in update.get("messages", []):
                    mtype = m.__class__.__name__
                    if mtype == "AIMessage":
                        text = m.content if isinstance(m.content, str) else " ".join(
                            b.get("text", "") for b in m.content if isinstance(b, dict))
                        text = text.strip()
                        for tc in (m.tool_calls or [{"name": "final_answer", "args": {}}]):
                            events.append({"thought": text,
                                           "action": {"name": tc["name"],
                                                      "args": tc.get("args", {})},
                                           "observation": None})
                            pending = events[-1]
                            print("[%4.0fs] turn %-2d %-12s %s"
                                  % (time.perf_counter() - t0, len(events),
                                     tc["name"], json.dumps(tc.get("args", {}))[:100]),
                                  flush=True)
                            if text:
                                print("         thought: %s" % text.replace("\n", " ")[:160],
                                      flush=True)
                            if tc["name"] == "done":
                                outcome = "done"
                    elif mtype == "ToolMessage" and pending is not None:
                        pending["observation"] = str(m.content)[:MAX_OBS_CHARS]
                        print("         obs: %s"
                              % str(m.content).replace("\n", " ")[:160], flush=True)
                        pending = None
            if len(events) >= MAX_TURNS:
                outcome = "budget_exhausted"
                print("budget of %d turns reached; stopping." % MAX_TURNS, flush=True)
                break
    except GraphRecursionError:
        # Budget exhaustion is a RESULT of the unstructured baseline, not a
        # crash: the 30 turns already collected are the artifact we came for,
        # so record them rather than losing them to the exception.
        outcome = "budget_exhausted"
        print("recursion limit reached; recording partial trajectory.", flush=True)
    return events, time.perf_counter() - t0, outcome


def run_stub(repo_dir):
    tools = {f.__name__: f for f in make_tools(repo_dir)}
    script = [
        ("I should find where divide is defined.",
         "search_repo", {"term": "divide"}),
        ("Read the file to see the bug.",
         "open_file", {"path": "calculator.py"}),
        ("Guard against zero and raise CalculatorError.",
         "edit_file", {"path": "calculator.py",
                       "old": "def divide(a, b):\n    return a / b\n",
                       "new": "def divide(a, b):\n"
                              "    if b == 0:\n"
                              "        raise CalculatorError('division by zero')\n"
                              "    return a / b\n"}),
        ("The fix is applied; submitting.",
         "done", {"summary": "guard divide(b==0) with CalculatorError"}),
    ]
    events = []
    t0 = time.perf_counter()
    for thought, name, args in script:
        obs = tools[name](**args)
        events.append({"thought": thought,
                       "action": {"name": name, "args": args},
                       "observation": obs})
    return events, time.perf_counter() - t0, "done"


# ---------------------------------------------------------------------------
# Behavior stats: understand the baseline before adding structure (D2).
# ---------------------------------------------------------------------------

def behavior_stats(events, wall, outcome):
    counts = {}
    repeats = 0
    seen = set()
    for e in events:
        counts[e["action"]["name"]] = counts.get(e["action"]["name"], 0) + 1
        key = json.dumps(e["action"], sort_keys=True)
        if key in seen:
            repeats += 1
        seen.add(key)
    reasoning_chars = sum(len(e["thought"]) for e in events)
    silent = sum(1 for e in events if not e["thought"])
    print("turns           : %d" % len(events))
    print("outcome         : %s" % outcome)
    print("tool usage      : %s" % json.dumps(counts))
    print("reasoning chars : %d (free text, unanchored)" % reasoning_chars)
    print("silent turns    : %d/%d (tool call with no thought text)"
          % (silent, len(events)))
    print("repeated actions: %d (identical name+args seen before)" % repeats)
    print("wall time       : %.1f s" % wall)


def make_stub_repo(root):
    if os.path.exists(root):
        shutil.rmtree(root)
    os.makedirs(root)
    open(os.path.join(root, "calculator.py"), "w").write(
        "class CalculatorError(Exception):\n    pass\n\n"
        "def divide(a, b):\n    return a / b\n")
    return root


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--repo-dir", default=None, help="local clone at base_commit")
    ap.add_argument("--instance-json", default=None,
                    help="instance file from fetch_swebench_lite.py --save")
    args = ap.parse_args()

    if args.stub:
        instance = STUB_INSTANCE
        repo_dir = make_stub_repo("sandbox_arm_a")
        events, wall, outcome = run_stub(repo_dir)
    else:
        if not (args.repo_dir and args.instance_json):
            sys.exit("live mode needs --repo-dir and --instance-json")
        instance = json.load(open(args.instance_json))
        repo_dir = args.repo_dir
        events, wall, outcome = run_live(instance["problem_statement"], repo_dir)

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "armA_trajectory.json")
    json.dump({"instance_id": instance.get("instance_id"),
               "model": MODEL,
               "outcome": outcome,
               "task": instance["problem_statement"],
               "events": events},
              open(path, "w"), indent=2)
    print("flat trajectory -> %s" % path)
    behavior_stats(events, wall, outcome)
    if args.stub:
        print("\nSTUB RUN: wiring check only. Nothing above is a result.")


if __name__ == "__main__":
    main()
