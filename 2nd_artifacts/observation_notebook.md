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
Status: single run.

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
Papers: the overthinking paper named in the meeting, exact cite to
confirm. New instances should be picked from its simple vs complex cases.
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
