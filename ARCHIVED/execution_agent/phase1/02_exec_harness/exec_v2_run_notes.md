# v2 structured pilot: freeze, run, judge

Internal notes. Written before the first v2 run so the success criteria
are on record ahead of the results.

## What changed in exec_harness.py

1. v2 tail clause, appended after the v1 sentence, structured cells only.
2. --tail {v1,v2} flag, default v1. v1 reproduces the banked instrument
   byte for byte. --tail v2 on any other config aborts.
3. Artifact records instrument_tail (structured only) and api_account.
4. v2 output filenames carry _tail-v2 so they can never collide with a
   banked v1 name. v1 naming unchanged.
5. The harness refuses to overwrite an existing artifact file.
6. Stale TODO comment removed (the emit-time parse it asked for already
   exists).

## Step 1: dry-run freeze (no tokens, your machine's numbers govern)

Reproduce v1 first. Both must print the banked hashes exactly:

```
python exec_harness.py --config structured_plan --provider anthropic --repo-dir <REPO> --instance-json .\request_file\astropy__astropy-12907.json --plan-file <CLAUDE_STRUCTURED_PLAN.json> --dry-run
python exec_harness.py --config structured_plan --provider openai --repo-dir <REPO> --instance-json .\request_file\astropy__astropy-12907.json --plan-file <GPT_STRUCTURED_PLAN.json> --dry-run
```

Expected: 822a94fca5388dcb... (claude) and 6f148063db230eb4... (gpt).
If either differs, stop, nothing runs.

Then the v2 freeze, same commands plus --tail v2. Container-predicted
hashes, to be confirmed by your machine:

```
claude structured v2: 014d0041e188da3e...
gpt structured v2:    d10c299b848eb4eb...
```

These were computed as sha256 of the banked prompt plus the appended
clause, after verifying the banked prompts end with the v1 tail. If your
dry-run prints anything else, stop and we compare.

Optional: dry-run the two unstructured cells. They should print their
banked hashes (595c42f2a43f7398 and 2878c0a88cf2720d) since nothing in
this change touches them.

## Step 2: live runs (structured only, school account)

Reset the checkout first, and between the two runs:

```
python setup_exec_repo.py --reset ...
```

Then:

```
python exec_harness.py --config structured_plan --provider anthropic ... --tail v2 --account school --run 1
python exec_harness.py --config structured_plan --provider openai ... --tail v2 --account school --run 1
```

Outputs land as ..._tail-v2_run1.json. The school key note (R8) is
covered by --account school going into the artifact.

## Step 3: judge against the pre-stated criteria

Success is contract compliance, not score:

1. Every tool-impossible policy gets an explicit stated-deviation record
   citing its "id". v1 baseline: one stated deviation total (gpt P7),
   two silent P1 skips.
2. Edit turns cite the deepest matching policy. v1 baseline: claude
   source edit filed under P3.1 while the patch policy is P4.
3. Valid-id attribution at or above the v1 rate per cell
   (claude 9/14, gpt 15/15).

Not criteria: whether the fix lands, token counts, or structured vs
unstructured comparisons.

If all three pass, the tail freezes at v2 even if numbers are ugly.
If one misses, one targeted reword, run v3, and that is the cap. A tail
needing a third rewrite is a finding about elicitability and goes to
the meeting instead of another iteration.

Every reword must stay generic. Nothing in the tail may reference
anything true only of this instance.

## Pilot hygiene

Pilots are kept, not ceremonied. No ARCHIVED prefix during iteration.
Only the frozen tail's runs feed the scorecard. The v1 to v2 delta
(skips become stated, mislabels stop or not) is itself material for the
explanation-fidelity track, so the pilot artifacts are data, not scrap.
