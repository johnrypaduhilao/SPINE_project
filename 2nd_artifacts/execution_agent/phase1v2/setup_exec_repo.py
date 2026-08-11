"""Execute arm, repository setup. Prepares the working checkout the exec
tools operate on, and restores it to pristine base state between runs.

Everything is read from the SWE-bench instance JSON: repo name and
base_commit are never typed by hand. The gold patch and test_patch are
NEVER applied here; they stay held out. The Docker evaluator applies them
later. This script only produces the repository state the agent sees.

Modes:
  setup (default)  clone if absent, fetch if present, checkout base_commit,
                   verify HEAD matches, verify the tree is clean.
  --reset          restore an existing checkout to pristine base_commit.
                   If the tree is dirty, the diff is archived to a
                   timestamped .patch file next to the checkout BEFORE
                   anything is destroyed, then hard reset + clean.

Run (PowerShell):
  python setup_exec_repo.py --instance-json <path> --dest C:\\work\\astropy_12907_repo
  python setup_exec_repo.py --instance-json <path> --dest C:\\work\\astropy_12907_repo --reset

Clone uses --filter=blob:none (partial clone): full history, blobs fetched
on demand at checkout. Use --full-clone to force a complete clone.
Requires git on PATH and network for the first setup.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


def run_git(repo_dir, *args, check=True):
    cmd = ["git"] + list(args)
    p = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)
    if check and p.returncode != 0:
        sys.exit("git %s failed:\n%s" % (" ".join(args), p.stderr.strip()))
    return p.stdout.strip()


def load_instance(path):
    inst = json.load(open(path, encoding="utf-8"))
    for field in ("repo", "base_commit", "instance_id"):
        if not inst.get(field):
            sys.exit("instance JSON missing field: %s" % field)
    return inst


def clone(repo_name, dest, full_clone):
    url = "https://github.com/%s.git" % repo_name
    cmd = ["git", "clone"]
    if not full_clone:
        cmd += ["--filter=blob:none"]
    cmd += ["--no-checkout", url, dest]
    print("cloning %s -> %s%s" % (url, dest,
          "" if full_clone else " (partial, blobs on demand)"))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("clone failed:\n%s" % p.stderr.strip())


def enforce_lf(repo_dir):
    # the exec tools and the Docker evaluator both require LF; Git for
    # Windows defaults to autocrlf=true, which smudges the tree to CRLF
    run_git(repo_dir, "config", "core.autocrlf", "false")
    run_git(repo_dir, "config", "core.eol", "lf")


def verify(repo_dir, base_commit, repo_name):
    head = run_git(repo_dir, "rev-parse", "HEAD")
    status = run_git(repo_dir, "status", "--porcelain")
    origin = run_git(repo_dir, "remote", "get-url", "origin", check=False)
    commit_date = run_git(repo_dir, "show", "-s", "--format=%ci", "HEAD")
    match = head == base_commit
    clean = status == ""
    sampled, crlf = 0, 0
    for dirpath, dirnames, filenames in os.walk(repo_dir):
        dirnames[:] = sorted(d for d in dirnames
                             if d != ".git" and not d.startswith("."))
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            try:
                raw = open(os.path.join(dirpath, fn), "rb").read()
            except OSError:
                continue
            sampled += 1
            if b"\r\n" in raw:
                crlf += 1
            if sampled >= 20:
                break
        if sampled >= 20:
            break
    print("checkout proof")
    print("  origin          : %s" % origin)
    print("  expected commit : %s" % base_commit)
    print("  HEAD            : %s" % head)
    print("  HEAD matches    : %s" % match)
    print("  tree clean      : %s" % clean)
    print("  commit date     : %s" % commit_date)
    print("  crlf .py files  : %d/%d sampled (must be 0)" % (crlf, sampled))
    if repo_name.split("/")[-1] not in origin:
        print("  WARNING: origin url does not contain %r" % repo_name)
    if not match:
        sys.exit("HEAD does not match base_commit; refusing to continue")
    if not clean:
        sys.exit("working tree is dirty; run --reset (diff is archived "
                 "first) or clean it by hand")
    if crlf:
        sys.exit("working tree has CRLF line endings; run --reset once "
                 "(the config is already corrected, reset re-materializes "
                 "the files as LF)")
    print("repository ready for the exec harness")


def do_setup(inst, dest, full_clone):
    fresh = not os.path.isdir(os.path.join(dest, ".git"))
    if fresh:
        if os.path.isdir(dest) and os.listdir(dest):
            sys.exit("%s exists, is not empty, and is not a git repo; "
                     "refusing to touch it" % dest)
        clone(inst["repo"], dest, full_clone)
        enforce_lf(dest)
    else:
        print("existing checkout at %s; fetching" % dest)
        enforce_lf(dest)
        run_git(dest, "fetch", "origin")
        # guard applies only to a tree that could hold unsaved agent edits;
        # a fresh --no-checkout clone has an empty tree by design
        status = run_git(dest, "status", "--porcelain")
        if status:
            sys.exit("working tree is dirty; run --reset first "
                     "(the diff is archived before anything is destroyed)")
    run_git(dest, "checkout", "--detach", inst["base_commit"])
    verify(dest, inst["base_commit"], inst["repo"])


def do_reset(inst, dest):
    if not os.path.isdir(os.path.join(dest, ".git")):
        sys.exit("%s is not a git checkout; nothing to reset" % dest)
    diff = run_git(dest, "diff", "HEAD")
    untracked = run_git(dest, "ls-files", "--others", "--exclude-standard")
    if diff or untracked:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = os.path.abspath(
            os.path.join(dest, os.pardir,
                         "reset_backup_%s_%s.patch"
                         % (inst["instance_id"], stamp)))
        with open(backup, "w", encoding="utf-8", newline="\n") as f:
            f.write(diff)
            if diff and not diff.endswith("\n"):
                f.write("\n")
        print("dirty tree archived -> %s (%d chars)" % (backup, len(diff)))
        if untracked:
            print("untracked files (removed by clean, NOT in the patch):")
            for line in untracked.splitlines():
                print("  %s" % line)
    else:
        print("tree already clean; resetting anyway for a known state")
    enforce_lf(dest)
    run_git(dest, "reset", "--hard", inst["base_commit"])
    # a line-ending config change does not reach already-materialized
    # files: git trusts its stat cache and skips rewriting them. Clearing
    # the index and resetting again forces every file through the current
    # config, so the tree really is LF afterwards.
    run_git(dest, "rm", "-rq", "--cached", ".")
    run_git(dest, "reset", "--hard", inst["base_commit"])
    run_git(dest, "clean", "-fd")
    verify(dest, inst["base_commit"], inst["repo"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance-json", required=True)
    ap.add_argument("--dest", required=True,
                    help="directory for the working checkout")
    ap.add_argument("--reset", action="store_true",
                    help="restore pristine base_commit (archives the diff first)")
    ap.add_argument("--full-clone", action="store_true",
                    help="complete clone instead of --filter=blob:none")
    args = ap.parse_args()

    inst = load_instance(args.instance_json)
    print("instance        : %s" % inst["instance_id"])
    print("repo            : %s" % inst["repo"])
    print("base_commit     : %s" % inst["base_commit"])

    if args.reset:
        do_reset(inst, args.dest)
    else:
        do_setup(inst, args.dest, args.full_clone)


if __name__ == "__main__":
    main()
