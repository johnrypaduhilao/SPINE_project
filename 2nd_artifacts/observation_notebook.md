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
Status: single run.

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