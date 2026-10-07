# Plan: provenance-gated memory writes for ExpeRepair

Code read: `ExpeRepair/ExpeRepair-v1.0` at commit `5594f2c` (2025-10-25). Line numbers below are from that commit and approximate. Re-check them before editing.

## 1. What the code does today (read from source)

### 1.1 Important correction to the premise
The public repo is **v1.0, a lightweight variant**. Its own README says it retrieves only demonstrations and does not use summarized insights. So in the shipped code:

- What gets pasted into later prompts is a **demonstration**: an agent-written test script pair (`old_test` / `new_test`) or a patch pair (`old_patch` / `new_patch`). It is not a text lesson.
- The lesson machinery exists only as leftovers:
  - `process_modifications_to_exps` (ADD / REMOVE / EDIT, capped at 15 per list) in `inference/generate_w_memory.py` ~77-120 and `api/review_manage_ase.py` ~456-500.
  - `convert_exp_json_to_str` (numbered list) in the same files and `agents/agent_reproducer.py` ~1269.
  - A prompt template with a `{summarized_rules}` slot, `agents/agent_reproducer.py` ~24-32, used by `_construct_init_thread_exp` (~743). Nothing calls that method.
  - `summarized_rules` call sites in `agents/agent_write_patch.py` (~445, 566, 690, 824, 874, 926) are commented out.
  - No code in the repo produces the ADD / REMOVE / EDIT instructions. The lesson generator is not released.

So the gate has two targets. **Target A (demonstrations)** exists in the shipped code and can be built and tested now. **Target B (lessons)** has to be reconstructed from the paper and the leftover scaffold. Build A first.

### 1.2 Write path (where "success" is decided)
| Store | Written at | What counts as success | Who decides |
|---|---|---|---|
| `reproduce_experiences.jsonl` | `agents/agent_reproducer.py` ~237-335 (first script) and ~343-470 (retries); entry built ~270-290 and ~396-410 | `filter_successful_experiences` (~1169-1205) keeps a pair when the later script's `if-reproduce == "YES"` | An LLM, via `_reproduction_is_correct` |
| `patch_experiences.jsonl` | `api/review_manage_ase.py` ~182 (path), ~230-245 (`new_result: True`), ~335-345 (`new_result: False`) | `filter_patch_experiences` (`agents/agent_write_patch.py` ~1221) keeps pairs with `new_result is True` | The agent's own reproduction test plus an LLM reviewer (`agent_reviewer.review_multiple_patch_select_best`) |

The project's real tests are never used as a write gate. `FAIL_TO_PASS` and `PASS_TO_PASS` sit in `task.py` (~379-380) and only go into metadata. This is correct for a benchmark: they are the scoring oracle, so the gate must not use them (see 4.3).

### 1.3 Read path (what gets pasted)
- `get_experiences` (`agent_reproducer.py` ~923-983) and `get_experiences_patch` (`agent_write_patch.py` ~1096-1140) rebuild a per-repo knowledge base, score it with BM25 (`top_k=10`), keep up to 3 distinct issues, and the prompt builders paste only the first one (`[:1]` at `agent_reproducer.py` ~827 and `agent_write_patch.py` ~728).
- The BM25 key is the **issue text** (`issue_description`, weights 0.6 / 0.4 on first retrieval). So an attacker who controls an issue controls what it will match.
- The pasted `new_test` / `new_patch` was generated from issue text and is stored verbatim.

### 1.4 Findings that change the design
1. **Untrusted text reaches memory unmarked.** Issue text flows into agent-written scripts and patches, which are stored with no source tags.
2. **Label noise is built in.** Success is an LLM judgement or the agent's own test, so wrong "successes" are written and retrieved.
3. **No time ordering.** `save_experiences` (~1208-1230) and `save_experiences_patch` (~1144-1165) read every task directory under the repo folder and skip only the current issue. An issue can retrieve memories from issues processed after it. The entries carry a `time` field that could be used for a cutoff. Verify this by running it.
4. **Model dependence.** Several stages call o4-mini (`common.set_gpto4_model`). Running with Qwen3-8B needs a new model class (see `model/register.py`, `model/gpt.py`).

## 2. The add-on in one paragraph
Tag every span in a candidate memory by where it came from. Issue text is **untrusted**. Repository files at the base commit, and output from executing the project's own existing tests, are **trusted**. A candidate is **promoted** to the pasteable tier only if trusted evidence carries it and its content is not mostly a paraphrase of the issue. Everything else stays in an **episodic-only quarantine tier** that is kept and logged but never pasted.

## 3. Design

### 3.1 Tiers
- `all.jsonl`: every candidate, with provenance fields and the gate decision (audit log).
- `promoted.jsonl`: the only file the read path may load.
- `quarantine.jsonl`: rejected candidates with the reason.

### 3.2 Span provenance
For each stored unit, split into spans (tokens, identifiers, string literals, code lines). Compute per span whether it is supported by:
- **Issue corpus**: the problem statement, including quoted code, tracebacks and comments.
- **Trusted corpus**: repo files the agent actually opened (via `SearchManager` and `bug_locs`), the project's existing test file for the instance (see 4.2), and stdout / stderr from running tests.

A span supported only by the issue corpus is tagged untrusted. A span supported by the trusted corpus is tagged trusted. LLM-written text with no source is tagged derived and inherits the tag of the evidence it cites (3.4).

### 3.3 Promotion rule (starting values, tune on a dev slice only)
Promote when all hold:
1. Trusted-supported fraction of content spans is at least `tau_t`.
2. Issue-only fraction is at most `tau_u`.
3. Execution evidence: for a demonstration, the candidate script fails before the patch and passes after, **and** the project's existing tests that cover the touched file show no new failures; for a patch pair, the selected patch passes those same checks.
4. No instruction-like content in untrusted-only spans (a cheap regex pass for imperatives and URLs is enough to start).

### 3.4 Lessons (Target B)
Require the lesson generator to emit evidence pointers (`file:line`, or a quoted test-output line). The gate resolves each pointer by exact lookup in the trusted corpus. A lesson with no resolvable trusted pointer, or whose text is mostly an issue paraphrase, stays in `quarantine.jsonl`. This makes "carried by trusted evidence" checkable instead of a judgement call.

### 3.5 Limits to state up front
- Lexical overlap is a heuristic. A careful paraphrase attack can beat it, so evaluate paraphrased attacks explicitly.
- A malicious file in the repo is trusted by definition. That is out of scope and should be reported as a limit.
- Using an LLM to judge provenance would reintroduce an attackable judge. Keep it out of the first version.

## 4. Implementation steps

### Phase 0: get a baseline running (days 1-4)
- [ ] Set up the testbed and repo structure per the README (Agentless repo-structure data, ACR testbed).
- [ ] Add a local-model class for Qwen3-8B behind an OpenAI-compatible endpoint (vLLM). Replace the o4-mini calls.
- [ ] Choose a dev slice of 20-30 SWE-Bench Lite issues from one large repo. Run reproduce, localize, generate, validate end to end with memory off.
- [ ] Add a stream-order switch: order issues by `created_at` from SWE-bench metadata and apply a time cutoff in both `save_experiences` functions. Compare against the unordered behaviour.
- **Exit:** baseline resolve rate on the dev slice, tokens per issue, and the count of memory entries written.

### Phase 1: instrument and measure label noise (days 5-8)
- [ ] At every write site in 1.2, add fields: `source_tags`, `issue_overlap`, `trusted_support`, `exec_evidence` (which tests ran, before / after return codes), `task_id`, `time`.
- [ ] Offline, score each "successful" entry against the SWE-bench oracle (`FAIL_TO_PASS` / `PASS_TO_PASS`, used only for analysis, never in the gate).
- **Exit:** how often LLM-judged success disagrees with the oracle. This number alone is a result worth showing.

### Phase 2: build the gate on demonstrations (days 9-14)
- [ ] New package `memory_gate/`: `provenance.py` (span tagging), `evidence.py` (build the trusted corpus per task), `gate.py` (promotion rule), `store.py` (three tiers).
- [ ] Add `--memory_mode {none,baseline,gated}` to `generate_initial.py`, `generate_w_memory.py`, `reproduce_initial.py`, `reproduce_w_memory.py`.
- [ ] Change the read path so `get_experiences` / `get_experiences_patch` load only `promoted.jsonl` in gated mode.
- [ ] Ablations: provenance-only gate, execution-only gate, both.
- **Exit:** promoted fraction, quarantined fraction, and resolve rate for baseline vs gated on the dev slice.

#### Phase 2 design

The gate is an offline filter on memory writes. At save time (after the LLM judges success), the candidate runs through the gate before being written to `promoted.jsonl`. Quarantined entries go to `quarantine.jsonl`. The read path (`get_experiences`, `get_experiences_patch`, `load_knowledge_base_patch`) in `--memory_mode gated` only loads `promoted.jsonl`.

The gate has three checks, each independently on/off:

1. **Provenance gate**: lexical overlap between candidate content and issue text. If the candidate patch or test is mostly a paraphrase of the issue statement, it's untrusted. Implementation: token Jaccard similarity of code lines against issue text. Threshold `tau_u = 0.65` (tune on dev slice).
2. **Execution gate**: the candidate's own reproduction test must change behavior (old≠new) and the patch must not fail the regression test file (from `swe_regression_test.json`). Implementation: parse `reproduce_outputs.jsonl` returncodes, check `swe_regression_test.json` for the regression test file path.
3. **Combined gate**: both checks must pass.

Gate mode is configurable via `--memory_mode`:
- `none`: no memory (current baseline)
- `baseline`: unmodified ExpeRepair (all LLM-judged successes)
- `gated`: only promoted entries
- `gated-provenance`: provenance-only
- `gated-execution`: execution-only

#### Files to create/modify

| File | Type | Change |
|---|---|---|
| `memory_gate/__init__.py` | New | Exports `gate_candidate`, `MemoryGateMode` |
| `memory_gate/provenance.py` | New | `compute_issue_overlap(issue_text, code_text) -> float` |
| `memory_gate/evidence.py` | New | `build_trusted_corpus(task) -> str`, `check_exec_evidence(task, test_file_path, before_rc, after_rc) -> bool` |
| `memory_gate/gate.py` | New | `gate_candidate(entry, gate_mode, task, test_file_path=None) -> (promoted: bool, reasons: list[str])` |
| `memory_gate/store.py` | New | Append-promote to `promoted.jsonl` or `quarantine.jsonl` |
| `config.py` | Modify | Add `memory_mode: str = "baseline"` |
| `agents/agent_reproducer.py:306-312` | Modify | Wrap the `json.dump` to `reproduce_experiences.jsonl` with gate + write to tier file |
| `api/review_manage_ase.py:287-294` | Modify | Same for patch_experiences |
| `agents/agent_reproducer.py:1208-1229` (`save_experiences`) | Modify | Read from promoted file in gated mode |
| `agents/agent_write_patch.py:1144-1167` (`save_experiences_patch`) | Modify | Same |
| `inference/generate_initial.py` | Modify | Accept `--memory_mode`, pass to ReviewManager |
| `inference/generate_w_memory.py` | Modify | Same |
| `inference/reproduce_initial.py` | Modify | Accept `--memory_mode`, pass to TestAgent |
| `inference/reproduce_w_memory.py` | Modify | Same |
| `agents/agent_reproducer.py` | Modify | `TestAgent.__init__` accepts `memory_mode` |
| `api/review_manage_ase.py` | Modify | `ReviewManager.__init__` accepts `memory_mode` |

#### Implementation order

1. Create `memory_gate/` package skeleton (init, store, provenance, evidence, gate)
2. Implement `provenance.py` — token Jaccard overlap between candidate spans and issue text
3. Implement `evidence.py` — read `swe_regression_test.json`, run the regression test, check before/after return codes
4. Implement `gate.py` — combine checks into promotion decision
5. Implement `store.py` — write to `promoted.jsonl` / `quarantine.jsonl`
6. Plumb `--memory_mode` through CLI → config → TestAgent/ReviewManager
7. Wrap the two write sites with gate call
8. Modify the two read paths (`save_experiences`, `save_experiences_patch`, `get_experiences`, `get_experiences_patch`, `load_knowledge_base_patch`)
9. Run full Phase 0 slice with `--memory_mode gated`
10. Run `analysis/measure_label_noise.py` comparing promoted vs baseline

### Phase 3: attack suite (days 15-20)
- [ ] Seed attacks into the problem statements of earlier issues in the stream:
  1. A planted fix recipe (for example "add a try/except that swallows the error" or a network call in the test script).
  2. A paraphrased version of the same recipe.
  3. An issue written to match a later issue's BM25 key.
- [ ] Measure: poisoned entries written, promoted, retrieved, adopted in a later patch, and benign memories lost.
- [ ] Record the repo-file case separately as the known limit.

### Phase 4: lessons (days 21-30, Target B)
- [ ] Reconstruct the summarize-and-update step following the paper's ADD / REMOVE / EDIT description. Reuse `process_modifications_to_exps` and the 15-item cap.
- [ ] Wire `_construct_init_thread_exp` and the `{summarized_rules}` slot (reproducer ~24-32, ~743), and restore the commented patch-prompt sites.
- [ ] Add evidence pointers (3.4) and gate lessons the same way.
- [ ] State clearly in any write-up that the lesson generator is a reconstruction.

## 5. Evaluation

| Condition | Memory |
|---|---|
| C0 | None |
| C1 | ExpeRepair as shipped (all LLM-judged successes) |
| C2 | Gated: provenance + execution |
| C3 | Execution-only gate |
| C4 | Provenance-only gate |

Metrics:
- Resolve rate on the held-out stream (SWE-bench harness, final scoring only).
- Label-noise rate of written entries (Phase 1).
- Attack success rate, persistence (how many later issues a poisoned entry affects), and benign preservation.
- Tokens and latency per issue.
- Promoted fraction, to show the gate is not just discarding everything.

Success criteria to fix before looking at results: the gate cuts attack success substantially while keeping at least most of the baseline memory's resolve-rate lift. Agree the exact numbers with Prof. Wang.

## 6. Risks and unknowns
- [ ] **Sparse memory with Qwen3-8B.** If few reproductions succeed, there is little to promote. Mitigation: a seed set run with a stronger model, reported separately.
- [ ] **`swe_regression_test.json` provenance.** It maps each instance to existing test files. Check how it was built. If it came from the benchmark's test patch, the file may be a hidden test and cannot serve as trusted evidence.
- [ ] **Benchmark leakage.** Earlier issues in a repo may contain fixes for later ones. Use leakage-filtered instances and the time cutoff.
- [ ] **Newer related work.** AdaRepair-Mem (2609.20130), PMCoder (2608.06811), MemoryGraft (2512.16962), MemSecBench (2607.27080). Differentiate before writing up.
- [ ] **Compute cost.** Each issue makes many model calls. Budget before scaling past the dev slice.

## 7. What to show Prof. Wang first
Phases 0 and 1 plus one poisoned-issue demo from Phase 3: a baseline replication, the measured label-noise rate, and one planted entry shown being written, retrieved and then quarantined by the gate. That is roughly two weeks and answers the question he is most likely to ask: does this change anything measurable?

## 8. Decisions needed
1. Start with Target A (demonstrations, runs on shipped code) and defer lessons to Phase 4. Recommended.
2. Confirm the compute and API budget for the dev slice.
3. Confirm the dev repo and slice size.
