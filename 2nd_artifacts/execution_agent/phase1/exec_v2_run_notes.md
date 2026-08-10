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

## v4 (tagged container, cut after the v3 walk)

What changed: for --tail v4 the structured tail is REPLACED, not
appended. The [P<id>] prefix contract is gone. Instead every tool call
must include <policy_id>ID</policy_id> and
<policy_action>ACTION</policy_action>, where ACTION is the cited
policy's "action" field copied from the plan. Tags parse anywhere in
the thought, so heading habits stop costing attribution. The
reconciliation-before-done clause is kept unchanged (it worked).
Thought text stays unwrapped. Records under v4 carry a new additive
field policy_action_echo holding the raw echoed verb (null when the
tag is missing).

Hypothesis on record before the run: the v1-v3 mislabels bind the
label to the thought because the tag lives at the front of the
thought. Binding the id to the action, with the verb echo forcing a
tree lookup, tests whether the mislabel is a binding artifact or a
real conceptualization. Either answer is a finding.

Criteria, updated for v4:
1. Reconciliation at done still present in both cells (regression
   check on the v3 win).
2. The source-edit turn carries the patch policy (C: P4, G: P6) in
   policy_id, and the echoed verb describes the tool call.
3. Parsed attribution at or above each cell's v1 rate (C 9/14,
   G 15/15), now measured on the tag parser.
Echo consistency (echo == cited node's action field) is a scoring
check, not a harness judgment.

Freeze expectations (dry-run, your machine governs):
  v3 regression: C ee86d2b1bd15183d..., G 78eaf0261f058a41...
  C-struct v4: 67fabf9f34966670e67634b8c1a8aa87f21e66efdf0159d38888fec963d76b35  chars 10749
  G-struct v4: a66616507f1ba6b486f30298985af1acf9b3308a6d37461876f3708321f78387  chars 8693

Live: reset, C-struct --tail v4 --account school, reset, G-struct
same. Artifacts land as _tail-v4_run1.json, destined for
03_exec_harness. v4 is the last rung before the meeting; the four-rung
ladder ships as a package.

## v5 (clean register, cut after the v4 walk)

Same semantics as v4 (tags anywhere, verb echo, impossibility clause,
reconciliation before done) plus the deepest-policy clause restored,
rewritten as clean bullets instead of one dense paragraph. ASCII only.
Parser unchanged from v4.

Hypothesis on record: presentation register drives compliance. GPT was
perfect under the terse prefix three times and broke under the dense
tag paragraph; it should recover under clean structure. Claude should
hold its v4 placement fix.

Decision rule, fixed before the run: v5 locks as the phase-2 tail only
if BOTH models come in at or above their v1 floors (C 9/14, G 15/15)
with reconciliation intact. Otherwise v4 and v5 both go to the meeting
and it picks. No v6 either way. The edit-turn phase lag is expected to
persist; if it does, that is a fifth replication, not a v5 failure.

Freeze expectations (dry-run, your machine governs):
  C-struct v5: 04ac4dfff31fb7ec04955c2625af74f562b2b7f8c2b9cd83f27aab59bfd07663  chars 10909
  G-struct v5: e3cff96cf3c0f08a9273b298b382502dba70c9052c2ea8fc734ec4cfa2e780d0  chars 8853

Live: reset, C-struct --tail v5 --account school, reset, G-struct
same. Artifacts land as _tail-v5_run1.json, destined for
05_exec_harness.