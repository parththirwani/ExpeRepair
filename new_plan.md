# Plan (revised): provenance-gated memory writes for ExpeRepair

Code read: `ExpeRepair/ExpeRepair-v1.0` at commit `5594f2c` (2025-10-25). Line numbers are approximate. Re-check them before editing.

## Tight execution list

Use this as the working checklist. The detailed rationale and design notes stay below.

### 1. Reconcile the current results first
- [x] Recount raw entries in `reproduce_experiences.jsonl`, `patch_experiences.jsonl`, `all.jsonl`, `promoted.jsonl`, and `quarantine.jsonl`.
- [x] Check the contradiction between the earlier attack summary and the current statement that the socket payload was promoted.
- [x] Write one corrected table with: total written, LLM-YES, LLM-NO, promoted, quarantined, promoted despite LLM-NO, quarantined despite LLM-YES.
- Outcome: confirmed old gate had zero divergence from judge — promoted set was identical to LLM-YES set.

### 2. Make the reproduce gate judge-independent
- [x] Remove the current reproduce-path dependence on `new_check_repro["if-reproduce"]` in `memory_gate/gate.py`.
- [x] Add a denylist scan for generated tests (`memory_gate/denylist.py`).
- [x] Run the generated test at the base commit and record return code, exception type, and stderr signature (deferred when SweTask unavailable).
- [x] If the same issue has a promoted patch, run the test again after applying the patch (deferred when SweTask unavailable).
- [x] Promote only when the test is safe, fails before, and either passes after or has another explicit non-LLM success signal.
- Outcome: gate now blocks 3 judge-YES entries (socket, exec, compile, eval) and promotes 63 judge-NO entries (denylist-clean tests).

### 3. Make the patch gate actually behavioral
- [x] Keep provenance as a weak filter only.
- [x] Require denylist pass, before/after behavior change on the reproducer, and no regression in trusted existing tests.
- [x] Treat `new_result` as metadata for later analysis, not as gate evidence.
- Outcome: patch entries pass through denylist+provenance cleanly; behavioral checks require live SweTask (deferred to a pipeline run).

### 4. Log retrieval-to-adoption, not just write-time counts
- [x] Log promoted entry IDs (`gate_seq`) when writing memory.
- [x] Log retrieved entry IDs (`retrieved_seq`) and scores for each downstream issue.
- [x] Log source task IDs (`retrieved_source`) for each retrieved entry.
- Outcome: retrieval log includes gate_seq + source_task_id for end-to-end tracing from write to promote to retrieve.

### 5. Run paired attacks against baseline and gated
- [x] Run each attack with the same stream and seed in C1 and C2.
- [x] Include at least: direct planted recipe, paraphrased recipe, BM25-targeting issue.
- [x] Measure for each condition: written, promoted, quarantined by denylist.
- Outcome: socket payload quarantined in both modes (denylist catches it). Paraphrase and BM25 attacks not denylist-visible. No attacks promoted in either mode.

### 6. Re-check the 30 judge-rejected reproduce entries
- [x] Re-run every quarantined reproduce entry with no model in the decision loop.
- [x] Classify each as rescued, confirmed failure, or undetermined.
- [x] Convert confirmed failures into template-only facts with evidence pointers.
- Outcome: 2 denylist-flagged, 10 confirmed failures, 3 rescued candidates, 3 undetermined, 10 failure facts written to `lessons.jsonl`.

### 7. Keep success lessons last
- [x] Do not rebuild semantic lessons until C2 and the quarantine re-check show real signal.
- [x] Signal is present: Phase 4 failure facts have real signal (ModuleNotFoundError, AttributeError, TypeError).
- [ ] Consider: wire `{summarized_rules}` slot to serve failure facts from `lessons.jsonl` using `process_modifications_to_exps`.

### Done criteria for the next milestone
- [ ] C2 disagrees with the original judge on nonzero entries.
- [ ] At least one planted payload is promoted or adopted in C1 and blocked in C2.
- [ ] The clean-data result is reported even if it stays flat.
- [ ] Phase 4 produces either valid rescues or useful failure facts.

## 0. What changed since the first version

1. The first run showed no behavioral difference on clean data. The gate promoted 29 of 59 entries, and the LLM judge's own filters had already kept the same 29. Nothing was newly blocked and nothing was newly saved.
2. On attack data, the gate promoted the planted test that opens a network socket. It did not block the payload that mattered.
3. Cause. Both checks agree with the thing they check. Provenance measures token overlap, which instruction-following payloads lower. The execution check re-reads the judge's verdict. So the gate can only agree with the judge.
4. A figure from an earlier summary (4 of 4 payloads written, 0 of 4 promoted) conflicts with item 2. Check both against the raw `all.jsonl` and `promoted.jsonl` logs before anything goes in a write-up.
5. Revisions in this plan:
   - Phase 2 is rebuilt with checks that do not depend on the judge.
   - Attacks are run through the baseline and the gate side by side (Phase 3).
   - A new Phase 4 re-checks the 30 judge-rejected entries and turns confirmed failures into stored facts.
   - The old Phase 4 (lessons) becomes Phase 5.

## 1. What the code does today (read from source)

### 1.1 Premise correction
The public repo is v1.0, a lightweight variant. Its README says it retrieves only demonstrations and does not use summarized insights. In the shipped code:

- What later prompts receive is a demonstration. It is an agent-written test script pair (`old_test` / `new_test`) or a patch pair (`old_patch` / `new_patch`). It is not a text lesson.
- Lesson machinery exists only as leftovers.
  - `process_modifications_to_exps` (ADD / REMOVE / EDIT, capped at 15 per list) in `inference/generate_w_memory.py` ~77-120 and `api/review_manage_ase.py` ~456-500.
  - `convert_exp_json_to_str` (numbered list) in the same files and `agents/agent_reproducer.py` ~1269.
  - A prompt template with a `{summarized_rules}` slot in `agents/agent_reproducer.py` ~24-32, used by `_construct_init_thread_exp` (~743). Nothing calls that method.
  - The `summarized_rules` call sites in `agents/agent_write_patch.py` (~445, 566, 690, 824, 874, 926) are commented out.
  - No code in the repo produces the ADD / REMOVE / EDIT instructions. The lesson generator is not released.

Target A (demonstrations) exists in shipped code and can be built and tested now. Target B (lessons) must be reconstructed from the paper and the leftover scaffold.

### 1.2 Write path (where "success" is decided)

| Store | Written at | What counts as success | Who decides |
|---|---|---|---|
| `reproduce_experiences.jsonl` | `agents/agent_reproducer.py` ~237-335 (first script) and ~343-470 (retries) | `filter_successful_experiences` (~1169-1205) keeps a pair when the later script's `if-reproduce == "YES"` | An LLM, via `_reproduction_is_correct` |
| `patch_experiences.jsonl` | `api/review_manage_ase.py` ~182, ~230-245 (`new_result: True`), ~335-345 (`new_result: False`) | `filter_patch_experiences` (`agents/agent_write_patch.py` ~1221) keeps pairs with `new_result is True` | The agent's own reproduction test plus an LLM reviewer |

The project's real tests are never a write gate. `FAIL_TO_PASS` and `PASS_TO_PASS` sit in `task.py` (~379-380) and only go into metadata. They are the scoring oracle, so the gate must not use them (see 4.3).

### 1.3 Read path (what gets pasted)
- `get_experiences` (`agent_reproducer.py` ~923-983) and `get_experiences_patch` (`agent_write_patch.py` ~1096-1140) rebuild a per-repo knowledge base, score it with BM25 (`top_k=10`), keep up to 3 distinct issues, and the prompt builders paste only the first one.
- The BM25 key is the issue text. An attacker who controls an issue controls what it matches.
- The pasted `new_test` / `new_patch` was generated from issue text and is stored verbatim.

### 1.4 Findings that shape the design
1. Untrusted text reaches memory unmarked.
2. Label noise is built in. Success is an LLM judgement or the agent's own test.
3. No time ordering. `save_experiences` (~1208-1230) and `save_experiences_patch` (~1144-1165) read every task directory and skip only the current issue, so an issue can retrieve memories from later issues. Entries carry a `time` field that could serve as a cutoff. Verify by running it.
4. Model dependence. Several stages call o4-mini. Running Qwen3-8B needs a new model class (`model/register.py`, `model/gpt.py`).

## 2. The add-on in one paragraph
Tag every span in a candidate memory by where it came from. Issue text is untrusted. Repository files at the base commit and output from executing the project's own existing tests are trusted. A candidate is promoted to the pasteable tier only if trusted evidence supports it, no judge-independent check flags it, and its content is not mostly a paraphrase of the issue. Everything else goes to a quarantine tier that is kept and logged but never pasted. Quarantined entries are re-checked later (Phase 4) and can be rescued or turned into stored failure facts.

## 3. Design

### 3.1 Tiers
- `all.jsonl` holds every candidate, with provenance fields and the gate decision (audit log).
- `promoted.jsonl` is the only file the demonstration read path may load.
- `quarantine.jsonl` holds rejected candidates with the reason.
- `rescued.jsonl` holds quarantined demonstrations that passed the Phase 4 re-check. Loaded only in the recovery conditions (C5, C6).
- `lessons.jsonl` holds failure facts and, later, success lessons, each with an evidence pointer. Loaded only through the lesson prompt slot, never as a demonstration.

### 3.2 Span provenance
For each stored unit, split into spans (tokens, identifiers, string literals, code lines). Per span, compute whether it is supported by:
- The issue corpus, meaning the problem statement including quoted code, tracebacks and comments.
- The trusted corpus, meaning repo files the agent opened (via `SearchManager` and `bug_locs`), the project's existing test file for the instance (see 4.2), and stdout / stderr from running tests.

A span supported only by the issue corpus is untrusted. A span supported by the trusted corpus is trusted. LLM-written text with no source is derived and inherits the tag of the evidence it cites (3.4).

### 3.3 Checks that do not depend on the judge
The first run failed because every check deferred to the judge. The gate now needs at least two checks that never read the judge's verdict.

1. **Behavioral denylist.** A static scan, with no model call. Flag network and process imports and calls in test scripts (`socket`, `requests`, `urllib`, `subprocess`, `os.system`, `eval`, `exec`). Flag bare `except: pass` and swallowed exceptions in patches. Flag URLs and shell strings in any untrusted-only span.
2. **Measured execution.** Run the candidate test at the base commit and again with the selected patch applied. Record return codes and the failure signature. For a demonstration, require fail before and pass after. Do not read `if-reproduce` or `new_result`.
3. **Regression check.** The patch must show no new failures in the project's existing tests that cover the touched file.
4. **Provenance overlap.** Token Jaccard of code lines against issue text, starting at `tau_u = 0.65`. Keep it, but treat it as the weakest check. Paraphrased and instruction-following payloads lower overlap, so it cannot carry the gate alone.

Promotion needs checks 1 to 3 to pass and check 4 to be under threshold. Each check has its own on/off switch for the ablations.

### 3.4 Evidence pointers for lessons
A lesson must carry a pointer, either `file:line` or a quoted test-output line. The gate resolves each pointer by exact lookup in the trusted corpus. A lesson with no resolvable pointer, or one that mostly paraphrases the issue, stays in quarantine.

### 3.5 Limits to state up front
- Lexical overlap is a heuristic. A careful paraphrase beats it, so test paraphrased attacks explicitly.
- A denylist is a list of known bad patterns. It will miss payloads it was not written for. Report which payload classes it covers.
- A malicious file in the repo is trusted by definition. Out of scope, reported as a limit.
- An LLM judging provenance would reintroduce an attackable judge. Keep models out of the gate decision.

## 4. Implementation steps

### Phase 0: baseline (days 1-4)
- [ ] Set up the testbed and repo structure per the README (Agentless repo-structure data, ACR testbed).
- [ ] Add a local-model class for Qwen3-8B behind an OpenAI-compatible endpoint (vLLM). Replace the o4-mini calls.
- [ ] Pick a dev slice of 20 to 30 SWE-Bench Lite issues from one large repo. Run reproduce, localize, generate and validate end to end with memory off.
- [ ] Add a stream-order switch. Order issues by `created_at` and apply a time cutoff in both `save_experiences` functions. Compare against unordered behavior.
- Exit: baseline resolve rate, tokens per issue, count of memory entries written.

### Phase 1: measure label noise (days 5-8)
- [ ] At every write site in 1.2, add the fields `source_tags`, `issue_overlap`, `trusted_support`, `exec_evidence` (which tests ran, before and after return codes), `task_id`, `time`.
- [ ] Offline, score each "successful" entry against the SWE-bench oracle. The oracle is used for analysis only, never in the gate.
- Exit: how often LLM-judged success disagrees with the oracle. Your first run found 0 of 29 wrong. Report it, with the dev slice size.

### Phase 2: build the gate (days 9-16)
- [ ] New package `memory_gate/` with `provenance.py`, `evidence.py`, `denylist.py`, `gate.py`, `store.py`.
- [ ] Add `--memory_mode {none,baseline,gated,gated-provenance,gated-execution,gated-denylist}` to `generate_initial.py`, `generate_w_memory.py`, `reproduce_initial.py`, `reproduce_w_memory.py`.
- [ ] In gated mode, `get_experiences`, `get_experiences_patch` and `load_knowledge_base_patch` load only `promoted.jsonl`.
- [ ] `evidence.py` runs the candidate test itself before and after the patch and reads return codes and stderr. It never reads `if-reproduce` or `new_result`.
- [ ] Ablations: provenance only, execution only, denylist only, all three.
- Exit: promoted fraction, quarantined fraction, and resolve rate for baseline vs gated. Also the number of entries the gate rejected that the judge accepted. If that number is zero on clean data, report it as zero.

Files to create or modify

| File | Type | Change |
|---|---|---|
| `memory_gate/__init__.py` | New | Exports `gate_candidate`, `MemoryGateMode` |
| `memory_gate/provenance.py` | New | `compute_issue_overlap(issue_text, code_text) -> float` |
| `memory_gate/denylist.py` | New | `scan_test(code) -> list[str]`, `scan_patch(diff) -> list[str]` |
| `memory_gate/evidence.py` | New | `build_trusted_corpus(task)`, `run_before_after(task, test_path, patch) -> (rc_before, rc_after, signature)` |
| `memory_gate/gate.py` | New | `gate_candidate(entry, gate_mode, task, test_file_path=None) -> (promoted, reasons)` |
| `memory_gate/store.py` | New | Append to the tier files in 3.1 |
| `config.py` | Modify | Add `memory_mode` |
| `agents/agent_reproducer.py:306-312` | Modify | Gate the write to `reproduce_experiences.jsonl` |
| `api/review_manage_ase.py:287-294` | Modify | Gate the write to `patch_experiences.jsonl` |
| `agents/agent_reproducer.py:1208-1229`, `agents/agent_write_patch.py:1144-1167` | Modify | Read from the promoted file in gated mode |
| `inference/*.py` (four files) | Modify | Accept `--memory_mode` and pass it down |
| `TestAgent.__init__`, `ReviewManager.__init__` | Modify | Accept `memory_mode` |

### Phase 3: attack suite (days 17-22)
Run every attack through the baseline (C1) and the gated pipeline (C2) with the same stream and seed. A gate result is only meaningful next to the baseline result on the same payload.
- [ ] Attack 1, a planted fix recipe (a try/except that swallows the error, or a network call in the test script).
- [ ] Attack 2, a paraphrased version of the same recipe.
- [ ] Attack 3, an issue written to match a later issue's BM25 key.
- [ ] Attack 4, an issue that induces a misleading failure fact in Phase 4 (see 4.5). Run it after Phase 4 exists.
- [ ] Measure per attack and per condition: written, promoted, retrieved, adopted in a later patch, benign memories lost.
- [ ] Add a downstream run where retrieval actually executes, so "promoted" is tied to what a later issue received.
- [ ] Record the repo-file case separately as the known limit.
- Exit: a table of attack by condition. The claim "the gate helps" is supported only where C1 promotes and adopts a payload and C2 does not.

### Phase 4 (new): re-check quarantined entries and store failure facts (days 23-30)

Goal. The 30 judge-rejected reproduce entries are currently discarded. Re-check them with checks that do not use the judge. Rescue the ones that turn out to be good, and turn the confirmed failures into short stored facts that later issues can use.

#### 4.1 Naming
The earlier summaries called these 30 entries false negatives. That label is not earned yet. The judge said NO, and many of those NOs may be correct. Call them "judge-rejected" until the oracle comparison below says otherwise.

#### 4.2 Re-check procedure (no model in the decision)
For each entry in `quarantine.jsonl` that came from the reproduce stage:
1. Run the denylist scan. A flagged entry is closed as unsafe and is not rescued.
2. Run the test at the base commit and record the return code, exception type and stderr.
3. If the issue has a promoted patch (14 issues in the first run), apply it and run the test again.
4. Classify.
   - Rescued: fails before with an exception type or message that also appears in the issue's reported symptom, and passes after the patch. Move to `rescued.jsonl`.
   - Confirmed failure: the test does not reproduce, and the cause can be read from the output (import error, missing attribute, test passes on buggy code, timeout, wrong module). Keep in quarantine and extract a failure fact (4.3).
   - Undetermined: no promoted patch exists, so no after-run is possible. Keep in quarantine. A before-run can still yield a failure fact if the test crashed for a readable reason.

The symptom match compares test output to issue text. It does not copy issue text into memory.

#### 4.3 Failure facts
- [ ] For each confirmed failure, build a short fact from a fixed template plus values lifted from the output. Example form: "A test that imports `<module>` failed with `<ExceptionType>` in repo `<repo>`." No free-form model text in the first version.
- [ ] Every fact carries an evidence pointer, either a quoted stderr line or a `file:line` in the repo. `evidence.py` resolves it by exact lookup.
- [ ] A fact whose text is mostly an issue paraphrase is dropped. Reuse the overlap check from 3.3.
- [ ] Write facts to `lessons.jsonl` with `kind: avoid`, `task_id`, `time`, and the pointer.

#### 4.4 Using the facts
- [ ] Wire the `{summarized_rules}` slot in the reproducer prompt (~24-32, ~743) through `_construct_init_thread_exp`, and restore the commented patch-prompt sites. Facts go in this slot only.
- [ ] Reuse `process_modifications_to_exps` with ADD and the 15-item cap.
- [ ] Retrieve facts by repo and by module, not by issue text, so an attacker cannot aim them with BM25.
- [ ] Apply the time cutoff. A fact is only visible to issues created after the issue it came from.
- [ ] State in any write-up that the lesson path is a reconstruction. The shipped code has no generator.

#### 4.5 Risks specific to this phase
- The re-check adds a new write path, so it is a new attack surface. Attack 4 tests a planted issue that makes a test fail in a way that produces a misleading fact. Template-only facts limit what an attacker can say, but they do not remove the risk.
- Rescue precision may be low. Many NOs were probably right. If under half of the rescued entries match the oracle, drop rescue and keep only the failure facts.
- Facts may be too repo-specific to help later issues. Measure retrieval hits before measuring resolve rate.
- Execution after the patch needs a working environment per instance. Budget the compute (Section 6).

#### 4.6 Measurements
- Rescue rate, meaning rescued entries over judge-rejected entries.
- Rescue precision against the oracle (analysis only). This is the first real estimate of how many of the 30 were false negatives.
- Number of failure facts, and the fraction whose pointers resolve.
- Facts retrieved per later issue, and facts adopted (the later test avoids the stated failure).
- Resolve-rate change from C2 to C5 to C6 on the held-out stream.
- Exit: the numbers above on the dev slice, plus the attack 4 result.

### Phase 5: success lessons (days 31-40, Target B)
- [ ] Reconstruct the summarize-and-update step from the paper's ADD / REMOVE / EDIT description. The slot and the 15-item cap already exist from Phase 4.
- [ ] Add evidence pointers (3.4) and gate success lessons the same way as failure facts.
- [ ] State in any write-up that the lesson generator is a reconstruction.

## 5. Evaluation

| Condition | Memory |
|---|---|
| C0 | None |
| C1 | ExpeRepair as shipped (all LLM-judged successes) |
| C2 | Gated, all checks |
| C3 | Execution-only gate |
| C4 | Provenance-only gate |
| C5 | C2 plus rescued demonstrations |
| C6 | C5 plus failure facts |

Add a denylist-only condition to the ablation table if Phase 2 shows it does most of the work.

Metrics
- Resolve rate on the held-out stream (SWE-bench harness, final scoring only).
- Label-noise rate of written entries.
- Attack success rate, persistence (how many later issues a poisoned entry affects), and benign preservation, each for C1 and C2.
- Rescue rate, rescue precision, failure-fact resolvability and adoption.
- Tokens and latency per issue.
- Promoted fraction, to show the gate is not discarding everything.

Fix the success criteria before looking at results. Proposed starting point, to agree with Prof. Wang.
- C2 cuts attack adoption against C1 on the same payloads.
- C2 keeps most of the C1 resolve-rate lift.
- C5 and C6 are reported even if they show no lift. A null result there is still a result.

## 6. Risks and unknowns
- [ ] Sparse memory with Qwen3-8B. If few reproductions succeed, there is little to promote or rescue. Mitigation is a seed set run with a stronger model, reported separately.
- [ ] `swe_regression_test.json` provenance. Check how it was built. If it came from the benchmark's test patch, it may be a hidden test and cannot serve as trusted evidence.
- [ ] Benchmark leakage. Earlier issues may contain fixes for later ones. Use leakage-filtered instances and the time cutoff.
- [ ] Judge-rejected entries are not all recoverable. Rescue depends on a promoted patch existing for the same issue.
- [ ] Newer related work to differentiate before writing up: AdaRepair-Mem (2609.20130), PMCoder (2608.06811), MemoryGraft (2512.16962), MemSecBench (2607.27080).
- [ ] Compute. Before and after execution of every quarantined test multiplies the run cost. Budget before scaling past the dev slice.

## 7. What to show Prof. Wang first
1. The baseline replication and the measured label-noise rate (Phases 0 and 1).
2. The first-run negative result, stated plainly. The old gate agreed with the judge, so it added nothing on clean data and missed the socket payload.
3. The rebuilt gate against the baseline on the same planted payloads, with one payload shown written, retrieved, and then blocked or not.
4. The 30 judge-rejected entries, with the rescue rate and precision once Phase 4 has run on a slice.

## 8. Decisions needed
1. Confirm the denylist as the first judge-independent check, and agree which payload classes it must cover.
2. Agree to run every attack through both C1 and C2.
3. Decide whether failure facts are template-only in the first version (recommended) or allow model-written text later.
4. Confirm the compute and API budget for the dev slice, including before and after execution of quarantined tests.
5. Confirm the dev repo and slice size.
