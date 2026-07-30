import argparse
import json
import os
import shutil
import sys
import time

OUT_DIR = "outputs"
MODEL = "claude-sonnet-4-6"   # temperature 0, project convention
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
    from langchain_anthropic import ChatAnthropic
    from langchain.agents import create_agent

    #python -c "from langchain.agents import create_agent; a = create_agent('anthropic:claude-sonnet-4-6', []); print(type(a), type(a).__module__)"

    tools = make_tools(repo_dir)
    agent = create_agent(ChatAnthropic(model=MODEL, temperature=0), tools)

    prompt = (
        "You are a software engineering agent working in a repository at %s. "
        "Fix the following issue using the tools. When the fix is applied, "
        "call done with a one-line summary.\n\nISSUE:\n%s" % (repo_dir, intent)
    )

    events = []
    t0 = time.perf_counter()
    state = agent.invoke({"messages": [("user", prompt)]},
                         config={"recursion_limit": MAX_TURNS * 2})
    wall = time.perf_counter() - t0

    # Reconstruct the flat trajectory from the message history: for each AI
    # message, its free text is the thought and its tool calls the actions;
    # the following tool messages are the observations.
    msgs = state["messages"]
    pending = None
    for m in msgs:
        mtype = m.__class__.__name__
        if mtype == "AIMessage":
            text = m.content if isinstance(m.content, str) else " ".join(
                b.get("text", "") for b in m.content if isinstance(b, dict))
            for tc in (m.tool_calls or [{"name": "final_answer", "args": {}}]):
                events.append({"thought": text.strip(),
                               "action": {"name": tc["name"],
                                          "args": tc.get("args", {})},
                               "observation": None})
                pending = events[-1]
        elif mtype == "ToolMessage" and pending is not None:
            pending["observation"] = str(m.content)[:MAX_OBS_CHARS]
            pending = None
    return events, wall


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
    return events, time.perf_counter() - t0


# ---------------------------------------------------------------------------
# Behavior stats: understand the baseline before adding structure (D2).
# ---------------------------------------------------------------------------

def behavior_stats(events, wall):
    counts = {}
    for e in events:
        counts[e["action"]["name"]] = counts.get(e["action"]["name"], 0) + 1
    reasoning_chars = sum(len(e["thought"]) for e in events)
    print("turns           : %d" % len(events))
    print("tool usage      : %s" % json.dumps(counts))
    print("reasoning chars : %d (free text, unanchored)" % reasoning_chars)
    print("wall time       : %.1f s" % wall)
    print("budget hit      : %s" % ("YES" if len(events) >= MAX_TURNS else "no"))


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
        repo_dir = make_stub_repo("sandbox_unstructured")
        events, wall = run_stub(repo_dir)
    else:
        if not (args.repo_dir and args.instance_json):
            sys.exit("live mode needs --repo-dir and --instance-json")
        instance = json.load(open(args.instance_json))
        repo_dir = args.repo_dir
        events, wall = run_live(instance["problem_statement"], repo_dir)

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "unstructured_trajectory.json")
    json.dump({"task": instance["problem_statement"], "events": events},
              open(path, "w"), indent=2)
    print("flat trajectory -> %s" % path)
    behavior_stats(events, wall)
    if args.stub:
        print("\nSTUB RUN: wiring check only. Nothing above is a result.")


if __name__ == "__main__":
    main()
