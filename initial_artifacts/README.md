# SPINE: Artifact Bundle

Reproducibility package for the paper "SPINE: Structured Policy Refinement
with Intent-to-Execution Lineage." It contains the ground-truth refinement
trees, the evaluation prompts and scripts, the model outputs, the scorecards,
the domain ontologies, and the overhead benchmarks reported in the paper.

Scope: this README documents the artifact bundle only. It is not required by
the ICSE Research Track paper submission. It is provided so the bundle is
self-contained and reproducible.

## Environment

- Python 3 on Windows. PowerShell uses `python`; Git Bash uses `py`.
- Dependencies: `pip install langchain langchain-anthropic openpyxl rdflib`
- Set `ANTHROPIC_API_KEY` in the shell before running any evaluation script.
- Model: every refinement and evaluation run uses `claude-sonnet-4-6` through
  LangChain at temperature 0, so outputs are deterministic.
- Scoring is manual and authoritative. The scripts generate the model outputs;
  they do not compute the reported metrics. The scorecards (.xlsx) are the
  record of the manual scoring.

## Bundle contents

Top level:
- `generate_evaluation.py`        three-setting evaluation driver.
- `overhead_protect_files.py`     storage overhead, per-record byte sizes (Table V).
- `overhead_traversal_bench.py`   recovery cost, O(depth) traversal vs O(n) log scan (Sec V-D).
- `overhead_structuring_bench.py` one-time structuring cost per policy (Sec V-D).

`code_execution/`  (the fully worked domain)
- `ground_truth_protect_files.xlsx`  S1 ground truth: policy tree (Table I) and answer key (Table II).
- `request_corrected.txt`            Setting 3 structured prompt (the policy model).
- `setting2_code_execution_evaluation.py`  generates the unstructured (S2) output.
- `setting3_code_execution_evaluation.py`  generates the structured (S3) output.
- `setting2_output.txt`, `setting3_output.json`  the S2 and S3 model outputs.
- `provenance_scorecard.xlsx`        scoring: recall/precision (Table III), recoverability (Table IV), SIF.
- `old_langchain_provenance_eval.py` earlier evaluation script (superseded).

`av/`  (autonomous driving: speed cap, Law46)
- `ground_truth_av.xlsx`             S1 ground truth: 9-policy tree and answer key.
- `request_corrected_av.txt`         Setting 3 structured prompt.
- `eval_av.py`                       generates the S2 and S3 outputs.
- `setting2_output_av.txt`, `setting3_output_av.json`, `setting3_raw_av.txt`  the outputs.
- `provenance_scorecard_av.xlsx`     scoring: recoverability (Table IV), SIF.

`embodied/`  (in-progress third domain: stovetop cleaning)
- `ground_truth_embodied.xlsx`       S1 ground truth: 11-policy tree, 9-step answer key, references.
- `request_corrected_embodied.txt`   Setting 3 structured prompt.
- `setting2_embodied_evaluation.py`  generates the S2 output.
- `setting3_embodied_evaluation.py`  generates the S2 and S3 outputs.
- `setting2_output_embodied.txt`, `setting3_output_embodied.json`, `setting3_raw_embodied.txt`  the outputs.
- `provenance_scorecard_embodied.xlsx`  scoring: recoverability and SIF (coverage sheets are draft/supporting).

`ontologies/`
- `code_ontology.ttl`, `av_ontology.ttl`, `embodied_ontology.ttl`  the domain ontologies.
- `validate_ontology.py`             parses and validates the .ttl files with rdflib.
- `zhao_ttl/`                        the Toyota TI base ontologies (source of the AV vocabulary).

`AGENTSPEC_reproduction/`  (Sec IV-C runtime enforcement)
- `AgentSpec/src/`                   the reused reactive enforcement demo.
- `RESULTS/`                         enforcement run screenshots and text traces.

`AI_baseline/`  (supporting: multi-model refinement outputs)
- `code_execution_no_structure_testing/`  unstructured (S2) outputs from ChatGPT, Copilot, Gemini.
- `code_exeution_with_structure_testing/` structured (S3) outputs from Copilot, Gemini.
- `av_with_structure_testing/`            structured (S3) driving outputs from Copilot, Gemini.

`old/`  earlier overhead artifacts (superseded).

## Reproducing a result

1. Code S2/S3 outputs and recall/precision (Table III):
   `cd code_execution && python setting3_code_execution_evaluation.py`
   writes `setting2_output.txt` and `setting3_output.json`; score by hand
   against `ground_truth_protect_files.xlsx`, recorded in `provenance_scorecard.xlsx`.

2. Driving recoverability (Table IV, driving rows):
   `cd av && python eval_av.py`
   writes the S2 and S3 outputs; scored in `provenance_scorecard_av.xlsx`.

3. Embodied (third domain):
   `cd embodied && python setting3_embodied_evaluation.py`
   writes the S2 and S3 outputs; scored in `provenance_scorecard_embodied.xlsx`.

4. Storage overhead (Table V):
   `python overhead_protect_files.py`   reports 181 / 217 / 329 bytes (+36 O(1), +148).

5. Recovery and structuring cost (Sec V-D):
   `python overhead_traversal_bench.py`     O(depth) traversal vs O(n) log scan.
   `python overhead_structuring_bench.py`   about three microseconds per policy.

6. Ontology validation:
   `cd ontologies && python validate_ontology.py`

## Paper artifact map

- Table I  (code policy tree):            `code_execution/ground_truth_protect_files.xlsx` (tree sheet).
- Table II (code answer key):             `code_execution/ground_truth_protect_files.xlsx` (answer-key sheet).
- Table III (S2 vs S3 recall/precision):  `code_execution/provenance_scorecard.xlsx`.
- Table IV (recoverability, both domains): `code_execution/` and `av/` `provenance_scorecard*.xlsx`.
- Table V  (storage overhead):            `overhead_protect_files.py`.
- Figure 2 (S2 vs S3 tree comparison):    `code_execution/setting2_output.txt` and `setting3_output.json`.
- Sec IV-C (runtime enforcement):         `AGENTSPEC_reproduction/`.
- Sec V-D  (traversal, structuring cost): `overhead_traversal_bench.py`, `overhead_structuring_bench.py`.
