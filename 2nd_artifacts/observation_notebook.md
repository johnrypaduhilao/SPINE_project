# Observation notebook

Running list of things we saw in the runs. One entry per observation.
Every entry maps to one of the five problem tracks from the Aug 4 meeting:

1. refinement completeness / thoroughness
2. explanation and CoT fidelity (what it says vs what it does)
3. overthinking / analysis paralysis
4. traceability program (TC, AC, SIF)
5. lost in execution / token burn

Rules for entries: say what happened, point at the exact cell and anchor,
name the track, and be honest about status. Single run means we saw it once
on one instance. Replicated means we saw it again somewhere else. Nothing
here is "confirmed" unless Docker ran it.

Template:

```
## OB-XX short name
What happened:
Cells:
Anchor:
Track:
Papers:
Status:
```

---

## OB-01 precision maxes out once the thoroughness penalty is removed
What happened: after the Aug 4 re-ruling (beyond-intent-but-correct is not
penalized), every zero in the plan-stage precision sheets flipped. All four
zeros were tests or reporting. Nothing anywhere was actually off intent.
Precision is now 1.00 in all six cells, so on this instance it stopped
telling the representations apart. The separation lives in recall, TC/AC,
and SIF.
Cells: all six plan cells.
Anchor: scorecard_astropy12907_run2_FINAL.xlsx, Summary row 6 and
Open_rulings #12; flipped cells Precision_struct C12, C14, H13 and
Precision_unstr H10.
Track: 1.
Papers: to fill in the lit pass.
Status: single run.

## OB-02 structure seems to make refinement more thorough
What happened: the units that used to get penalized (design tests, add
tests, report results) came almost entirely from the structured cells. The
trees volunteer full engineering practice. The prose plans scored cleaner
partly by saying less. So what looked like an imprecision problem was
really a thoroughness signal.
Cells: C-struct (P3.2, P5), G-struct (P8), G-unstr (U6).
Anchor: same four cells as OB-01; Precision_struct A2 header states the
ruling.
Track: 1.
Papers: to fill in the lit pass.
Status: single run. The meeting asked us to check this at more intents.

## OB-03 plan content drove test authoring in every cell
What happened: the only plan with no test wording (Claude prose, zero
"test" mentions, computed) produced the only run without tests. The other
three plans mentioned tests and all three runs authored them. Execution
tracked plan content in all four cells.
Cells: all four exec cells.
Anchor: notes_exec_vs_plan_findings.md; exec artifacts, plan sections vs
authored files.
Track: 1, with a foot in 2.
Papers: to fill in the lit pass.
Status: replicated. All four planned phase1v2 cells on the fixed
harness track plan content: C-unstr (zero test wording, computed on the
canonical artifact) authored no tests; G-unstr (explicit two-test step)
authored both requested tests; both trajectory plans carry test wording
and both runs authored tests. The noplan cells sharpen rather than
contradict this: see OB-21.

## OB-04 same model, silent on prose, articulate on its tree
What happened: GPT wrote zero rationale turns under its prose plan (0 of
13) and a rationale on every turn under its tree (15 of 15). Claude went
5 of 7 on prose and 12 of 14 on its tree. Same models, same task, the
representation changed how much they explain themselves.
Cells: G-unstr vs G-struct, C-unstr vs C-struct.
Anchor: exec artifacts, per-turn thought fields;
scorecard_exec_astropy12907_phase1_DRAFT.xlsx Provenance_draft sheet.
Track: 2.
Papers: the 2025 reasoning-faithfulness paper from the meeting, exact cite
to confirm before it goes anywhere.
Status: single run.

## OB-05 perfect attribution is not the same as coverage
What happened: G-struct put a valid policy id on every record (15/15) but
only touched 5 of its 9 policies. C-struct attributed 9 of 14 records but
touched 6 of 11. So one side labels everything and covers less, the other
labels less and covers more. Both facts stay on the table, neither hides
the other.
Cells: C-struct, G-struct.
Anchor: exec scorecard DRAFT, Plan_adherence and Provenance_draft sheets.
Track: 4.
Papers: to fill in the lit pass.
Status: single run.

## OB-06 silent skip vs stated deviation
What happened: both structured runs silently skipped P1 (the
reproduce/monitor class, tool-impossible by design). GPT stated one
deviation out loud (t12, no command execution tool, citing P7). Claude
substituted silently at its P6. The base contract already says deviate
only with a stated reason, so the silent skips are non-compliance under an
existing instruction. The silence is the finding, not the skip.
Cells: C-struct, G-struct.
Anchor: exec artifacts t12 (G-struct); harness base prompt, deviation
clause.
Track: 2, feeds 4.
Papers: to fill in the lit pass.
Status: single run. Instrument v2 will test whether the silence goes away
when we ask for it explicitly.

## OB-07 a valid label can still be the wrong label
What happened: C-struct ran its source edit under [P3.1] (a design
policy) when the tree's patch policy is P4. The id parses, the node
exists, the audit chain works, and the label is still wrong. Validity is
not accuracy.
Cells: C-struct.
Anchor: exec artifact, the edit turn citing P3.1; plan tree, P4.
Track: 4, feeds 2.
Papers: to fill in the lit pass.
Status: replicated. The v2 rerun mislabeled the same edit again, under
[P2.2] this time. See OB-12 for what the two mislabels share.

## OB-12 the label follows the thought, not the tool call
What happened: on the turn where Claude applies the source fix, the
cited policy matches what the reasoning is doing, not what the tool call
does. In v1 the edit ran under [P3.1] with the thought "The bug is
confirmed... The fix is simple: change = 1 to = right" (a diagnosis
conclusion, labeled with a Plan node, while the action is the patch).
In v2 the same edit ran under [P2.2] with "Now I fully understand the
bug" (an analysis conclusion, same thing). Both times P4, the actual
patch policy, shows up late or never: v2 cites it on the verification
read after the edit, v1 never cites it. The v2 tail already said "cite
the most specific policy whose action the tool call performs" and the
model still labeled its cognitive phase. GPT does not show this: its
edits carry the right policy in both versions.
Cells: C-struct v1 (t6) and v2 (t5, t6).
Anchor: 01_exec_harness/outputs, C-struct artifact, t6 action.thought;
02_exec_harness/outputs, C-struct tail-v2 artifact, t5 and t6 thoughts.
Track: 2, feeds 4.
Papers: to fill in the lit pass. Candidate home is the reasoning
faithfulness track, since this is a gap between stated basis and
performed action.
Status: replicated four times (v1 through v4, same model, this
instance), and v4 settles the mechanism question. v4 moved the id out
of the thought prefix into action-bound tags with a verb echo copied
from the tree, and the mislabel survived the move: the source edit went
out as P3 with <policy_action>decide</policy_action> on an edit_file
call, and this time the test edit slid too (P3.2, design). The patch
and add labels landed on the verification reads one turn later. So the
labels lag the actions by one phase: the model stamps what its mind
just concluded, does the deed inside it, and credits the deed's policy
to the next look. Not a binding artifact, not a format problem. The
one v4 consolation: the echo makes these self-documenting, since
"decide" sitting on an edit flags itself without a manual walk.

## OB-08 the executor added a step the plan never asked for
What happened: Claude on its prose plan self-initiated a verification
re-read ("Let me verify the fix looks correct", t5) plus a trace-through
(t6). The prose plan has zero verify/confirm/check wording (computed). The
executor filled a gap the plan left open. GPT on prose had zero unplanned
turns.
Cells: C-unstr.
Anchor: exec artifact t5 and t6; plan text word check.
Track: 1, with a foot in 3.
Papers: to fill in the lit pass.
Status: single run.

## OB-09 retry loop in the trajectory plan
What happened: Claude's trajectory plan runs 34 steps and keeps re-opening
the same file. The thoughts admit it in places (step 17 retry admission,
step 24 "I've been trying to open the file multiple times", step 29 "I
keep getting the same result", step 33 "unable to see the file content").
GPT's trajectory does the same job in 8 steps. All 34 steps still scored
on intent, so this is not a precision problem, it is an efficiency and
overthinking problem.
Cells: C-traj (plan stage).
Anchor: scorecard_astropy12907_run2_FINAL.xlsx, Precision_traj rows 17,
24, 29, 33 notes.
Track: 3.
Papers: Cuadron et al. 2025, The Danger of Overthinking, arXiv
2502.08235. Confirmed against the pdf. Their released trajectories and
scores are the pool for picking new instances. One caution when mapping:
their rubric treats repeated retries as fine as long as the model waits
for feedback between tries, so our loop is closer to an efficiency
problem than to their overthinking definition. Their overthinking is
about preferring internal simulation over real feedback.
Status: single run.

## OB-10 structure costs tokens at execution time
What happened: same model, same instance, same one-line fix at the end.
Claude spent 29k tokens under prose and 128k under its tree. GPT spent 78k
under prose and 113k under its tree. The trees buy attribution and
articulate reasoning, and they pay for it in tokens and turns. Worth
measuring properly, not just noting.
Cells: all four exec cells.
Anchor: exec artifacts, per-turn usage fields; handoff numbers 29,031 /
127,649 / 77,773 / 112,982.
Track: 5, feeds 3.
Papers: to fill in the lit pass.
Status: single run.

## OB-11 the accountability cliff does not care about difficulty
What happened: TC and AC sit at 0 for unstructured and trajectory and 1
for structured, and that held across the three ICSE intents and again on
this instance. Coverage moves with task difficulty, the cliff does not.
The recoverability comes from the representation, not the model.
Cells: all plan cells, both studies.
Anchor: scorecard_astropy12907_run2_FINAL.xlsx Recoverability sheet; ICSE
scorecards, Recoverability sheets.
Track: 4.
Papers: to fill in the lit pass.
Status: replicated (three ICSE intents plus this instance).

## OB-13 the reconciliation clause works, and how they use it differs
What happened: v3 added one requirement: before calling done, account
for every uncited policy as completed, subsumed, or impossible. Both
models complied in full, and P1, silent in four straight structured
runs, finally got accounted in both. But the categories they picked
tell a story. GPT was blunt: P1 runtime reproduction "is impossible
because no command/test execution tool is available", P7 impossible,
P5 subsumed. Claude graded itself generously: P1 "Completed, observed
via code inspection", P6 "cannot run the test suite" only after listing
ten completions. Monitoring runtime behavior by reading source is a
stretch. Given three boxes, one model reaches for impossible and the
other reaches for completed.
Second thing worth keeping: Claude's accounting names P4 as completed
even though its edit turn was mislabeled (OB-12). So the intent-level
story is recoverable from the reconciliation even when the turn-level
label is wrong. The two layers fail independently.
Cells: C-struct v3 (t12), G-struct v3 (t12).
Anchor: 03_exec_harness artifacts, done-turn thoughts, both cells.
Track: 2, feeds 4.
Papers: to fill in the lit pass.
Status: single run per cell.

## OB-14 asking for more compliance cost the per-turn tagging
What happened: under v3 Claude's parsed attribution fell to 7/13,
below even the bare v1 tail (9/14). But two of the lost turns are not
missing tags, they are misplaced tags: t7 and t10 carry [P5] and [P6]
in the middle of the thought, after a markdown heading like "## Step 3",
so the prefix regex correctly refuses them. The behavior is there, the
format broke. Worth separating in any write-up: attribution behavior
(9 of 13 turns carry a tag somewhere) vs contract compliance (7 of 13
carry it where the contract says). GPT stayed at 13/13 with clean
prefixes. No causal claim from one run, but the direction is worth
watching: the run asked to do more accounting got sloppier at the
per-turn mechanics.
Cells: C-struct v3.
Anchor: 03_exec_harness C artifact, t7 and t10 thoughts; parse rule at
emit time in exec_harness.py.
Track: 2, feeds 4.
Papers: to fill in the lit pass.
Status: single run.

## OB-15 the two models traded places when the container changed
What happened: under the prefix contract (v1 to v3) GPT attributed
every single turn, three runs straight, while Claude kept dropping
tags. v4 swapped the prefix for anywhere-in-thought tags, and the two
swapped roles: Claude came back up to 9/13 (above its v1 rate, the
heading problem gone), GPT fell to 9/14, going bare on its
continuation reads and on done. Same models, same task, same plan,
only the attribution container changed. So there is no universally
better container between prefix and tags for these two models. GPT's
perfect streak was tied to the prefix ritual; Claude's failures were
tied to it. Elicitation format is a per-model property.
Both cells still reconciled in full at done, so the v3 win held
through the container change.
Cells: C-struct v4, G-struct v4, against v1 to v3.
Anchor: 04_exec_harness artifacts, per-turn policy_id and
policy_action_echo fields; the untagged G turns t3, t4, t5, t8, t13.
Track: 2, feeds 4.
Papers: to fill in the lit pass.
Status: single run per cell for v4; the prefix side is three runs.
Count correction (Aug 10): the v2 G cell is 16/16, not 15/15 as earlier
notes said; rate unchanged at 100%.

## OB-16 explaining the tags' purpose did not move the label
What happened: v6 kept the v5 tail byte for byte and added one paragraph
explaining why the tags exist (audit, traceability, an action with a
missing or wrong id cannot be traced), a 285-byte delta, single variable,
run at advisor direction outside the pre-stated five-rung ladder.
Prediction recorded at freeze: the purpose framing would not fix the
edit-turn mislabel. It held. Claude's source edit ran tagged P2.2 with
"Found the bug. On line 245", the seventh consecutive sample with the
source edit under a deliberation node (P3.1, P2.2, P2.2, P3, P2.2, P2.1,
P2.2). P4 appears in no record this run and shows up prose-only in the
done accounting. Test edit carried P5 correctly, reconciliation intact,
deeds 2/3. Knowing what the tags are for changed nothing about where the
label lands, which is what OB-12 predicted: the lag is behavioral, not
informational.
Cells: C-struct v6 (run 2, canonical; run 1 archived non-canonical,
harness recording defect).
Anchor: 06_exec_harness_run_2 C artifact, source-edit thought "Found the
bug. On line 245" (1 hit); '"policy_id": "P4"' 0 hits in the C artifact.
Track: 2, feeds 4.
Papers: to fill in the lit pass.
Status: single run for v6; the deliberation-node placement is seven
samples on this instance.

## OB-17 GPT's clean record broke on a frozen prompt
What happened: under v6 GPT recorded 13/13, but its source edit went out
tagged P3 (derive, a definitive policy) with P6 (modify) arriving on the
next verification read: the lag signature, in GPT, for the first time
(1 of 7 GPT samples; Claude 7 of 7). The prompt was dry-run frozen before
the call. One sample ended the "zero level violations for GPT" claim,
retired everywhere it appears. Working headline: self-reported
attribution is unstable within one model even on a byte-frozen prompt,
so per-model claims built on a handful of samples do not hold.
Cells: G-struct v6 (run 2, canonical).
Anchor: 06_exec_harness_run_2 G artifact, rec 8 thought "replaces a
right nested child matrix with ones".
Track: 2, feeds 4.
Papers: to fill in the lit pass.
Status: single run; the breaking sample against six prior clean ones.

## OB-18 first GPT reconciliation miss, and it is self-inconsistent
What happened: GPT's done turn under v6 was tagged P7 while the same
thought declares P7 impossible, and P8 was neither cited during the run
nor accounted at done. First GPT reconciliation miss after full
reconciliations in v3, v4, v5. The two layers OB-13 called independent
(turn labels, done accounting) failed in the same run, plus a third
shape: a tag that contradicts its own thought in the same breath.
Cells: G-struct v6 (run 2, canonical).
Anchor: 06_exec_harness_run_2 G artifact, done thought "Policy
accounting before completion" contains no P8; done record policy_id P7.
Track: 2, feeds 4.
Papers: to fill in the lit pass.
Status: single run.

## OB-19 the trajectory step list was not binding for either executor
What happened: first live trajectory cells (no-tag by construction).
Claude's trajectory plan contains zero edit steps (17 open, 16 search,
1 done); the fix exists only as prose in the plan's 3081-char done
summary. Executor Claude opened with "I'll follow the plan", then edited
source at t06 and tests at t10 with no stated deviation, despite the
standing "deviate only with stated reason" clause. The actionable
content lived in the plan's prose and the executor did the prose, not
the steps. GPT executed its plan's work but swapped the order, source
edit before test edit against its plan's steps 5 and 6, also unstated.
Both landed the gold one-line fix at the gold hunk and added a
nested-compound regression test; Docker pending, predictions logged
(both predicted to resolve). Test hunks: C at 135 again, consistent
with every prior C run; G at a fourth distinct location (138, after
148, 56, 113); neither overlaps the held-out test hunks at 28 and
52-59.
Cells: C-traj exec, G-traj exec (phase1v2, run 2 canonical; run 1
archived pre-truncation-fix, first sighting).
Anchor: phase1v2 00_TRAJECTORY outputs run 2 artifacts, C t00 thought
"I'll follow the plan", source edit t05, test edit t09, no deviation
statement anywhere; G t09/t10 edit order against plan parsed_steps 5
and 6. Same signals in the archived run 1 (C t06/t10, G t09/t10).
Track: 2, with a foot in 1 and 4.
Papers: to fill in the lit pass.
Status: replicated (both cells, archived run plus canonical rerun; the
plan-stage facts are single-artifact properties and hold regardless).

## OB-20 GPT went silent again once nothing asked it to talk
What happened: in the trajectory cells GPT's stored thoughts are empty
on all 12 turns; Claude wrote substantive thoughts on 9 of 14. This
extends OB-04 to a third representation: GPT at 0 of 13 on prose, 15 of
15 on its tagged tree, now 0 of 12 on trajectory. GPT explains itself
when the instrument demands it and not otherwise; Claude explains
regardless. Consequence for the reconstructed side: for a GPT no-tag
run the chain-of-thought component of the reconstruction material is
absent entirely, so prose reconstruction works from actions and
observations only. The baseline description in the paper should say so.
Cells: G-traj exec, C-traj exec (phase1v2, run 2 canonical; run 1
archived, first sighting); G-noplan, C-noplan (phase1v2).
Anchor: phase1v2 00_TRAJECTORY outputs run 2 artifacts, per-record
action.thought fields (G empty 12/12 in both runs; C substantive on
9/14 in run 1 and 8/13 in run 2); phase1v2 01_NOPLAN artifacts
(G empty 13/13, C substantive 7/12); phase1v2 02_UNSTRUCTURED
artifacts (G empty 14/14, C substantive 4/6).
Track: 2, feeds 4.
Papers: to fill in the lit pass.
Status: replicated across trajectory and noplan. The pattern now spans
four configurations: G at zero thoughts on prose, trajectory (twice),
and noplan, and at 15/15 only under its tagged tree. GPT explains when
the instrument demands it and not otherwise.


## OB-21 both executors authored tests with no prompting at all
What happened: the noplan cells contain zero test wording anywhere (the
prompt is the base contract plus the issue, 1490 chars, nothing else),
and both executors authored a regression test anyway (C test edit t10,
G test edit t11). This complicates OB-03's story. In the earlier four
cells, test authoring tracked plan test-wording, and the one plan with
no test wording (Claude prose) produced the only run without tests. The
noplan result shows absence of test wording is not the suppressor:
with no plan at all, Claude tests by default. Put together, the sharper
reading is that a plan's presence constrains behavior, and an
incomplete plan can suppress engineering practice the model would
otherwise do unprompted. Cross-generation caveat: the prose cells were
earlier samples on the earlier harness, so this is a contrast across
runs, not a controlled pair.
Cells: C-noplan, G-noplan (phase1v2); contrast cells C-unstr, G-unstr
(phase1v2).
Anchor: phase1v2 01_NOPLAN artifacts, C t10 and G t11 edit turns;
phase1v2 02_UNSTRUCTURED C artifact, 6 turns, no test-file touch in
the model_patch; the noplan prompt body (no PLAN header by
construction).
Track: 1, with a foot in 2.
Papers: to fill in the lit pass.
Status: replicated as a controlled pair. C-noplan and C-unstr ran in
the same session on the identical fixed harness, same instance, same
base contract: with no plan Claude authored a test unprompted; with a
test-free prose plan Claude authored none. The suppression reading no
longer rests on a cross-generation contrast.

## OB-22 the idiomatic test placement is the one that collides with the
held-out patch
What happened: the two models place their regression tests differently,
and the more idiomatic choice is the risky one. GPT appends a
standalone test function near the end of the test file in every run
(113, 138, 113 across its cells here). Claude under noplan integrated
its test INTO the existing parametrized compound_models dict at the
conventional location (line 52 region), which is exactly the region
the held-out test patch rewrites; under trajectory Claude appended
standalone at 135 instead, so plan presence also moved its placement.
Application rehearsal on a real checkout at base_commit, model_patch
first then held-out test_patch, per the Docker order: traj C run 2,
traj G run 2, noplan G, unstr C, and unstr G all apply cleanly end to
end; noplan C fails strict git apply on the test patch (hunk 2 at
line 52) and succeeds only through the patch fuzz fallback (fuzz 3,
offset 7), after which the duplicate cm8 dict key resolves in the
held-out version's favor by literal-order semantics. Docker
predictions logged: traj C, traj G, noplan G, unstr C, and unstr G
predicted to resolve; noplan C predicted to resolve contingent on the
evaluator's fuzz fallback, and would fail under a strict-git-apply-only
evaluator.
Cells: all six phase1v2 canonical exec cells.
Anchor: phase1v2 artifacts, test-edit hunk headers; application
rehearsal transcript (clone at d16bfe05, apply order, rc values).
Track: 1, feeds the Docker methodology notes.
Papers: to fill in the lit pass.
Status: single rehearsal per cell; nothing is confirmed until Docker
runs.


## OB-23 execution cost tracks prescribed scope, and the orderings
invert between models
What happened: with six canonical cells on one harness, the
cheapest-to-dearest ordering of plan representations is not
model-stable. Claude: unstructured 27,979 tokens (6 turns), noplan
69,143 (12), trajectory 178,225 (13). GPT: noplan 73,342 (13),
trajectory 77,769 (12), unstructured 88,071 (14). The same prose
representation is Claude's cheapest cell and GPT's dearest, and the
reasons are visible in the runs: Claude's prose plan named the bug
location and prescribed no tests, so Claude went nearly straight to
the fix; GPT's prose plan prescribed a two-test regression program
plus suite verification, and GPT executed all of it. Trajectory's cost
for Claude is dominated by its own 26k-char plan re-fed every turn.
So token cost confounds three things: the plan's size in context, the
scope of work the plan prescribes, and executor behavior. Any overhead
claim about a representation must hold the prescribed scope fixed or
say it did not. This complicates OB-10's structure-costs-tokens
reading rather than replacing it.
Cells: all six phase1v2 canonical exec cells.
Anchor: phase1v2 artifacts, usage_total fields and record counts per
cell; plan artifacts for the scope contrast (test wording computed:
C-unstr 0, G-unstr 7).
Track: 5, feeds 3 and 1.
Papers: to fill in the lit pass.
Status: single run per cell; the inversion is one instance, one run
each.