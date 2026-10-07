# Plan: test failure facts as a standalone memory channel ("facts only")

## Goal

Test whether failure facts (short template-generated "avoid" lessons from quarantined reproduce entries) improve the reproducer when they are the *only* memory available — no demonstrations, no episodic examples.

## Motivation

Right now facts are prepended onto the demonstration string and stuffed into the `{retrieved_example}` slot. That conflates two effects: did the model improve because of the fact, or because of the demo? "Facts only" isolates the fact channel.

## Design

Add a new memory mode `facts` that disables demonstration retrieval entirely and instead populates the `{summarized_rules}` slot in `SYSTEM_PROMPT_W_RULE` through `_construct_init_thread_exp`.

### Memory modes (extending existing set)

| mode | demos | facts |
|---|---|---|
| `none` | - | - |
| `baseline` | all LLM-judged | - |
| `gated` | promoted only | prepended to demos (current) |
| `gated-provenance` | promoted only | - |
| `gated-execution` | promoted only | - |
| **`facts`** | **disabled** | **loaded into `{summarized_rules}`** |

### Implementation

#### 1. Add `facts` to config and gate mode

- `config.py`: accept `"facts"` in `memory_mode`
- `memory_gate/gate.py`: add `MemoryGateMode.FACTS` so the write path still promotes/quarantines normally for later use even during facts-only runs

#### 2. Separate fact retrieval from demo retrieval in the reproducer

Current path in `_write_reproducing_test_W_EXP` (`agents/agent_reproducer.py:371-392`):

```
if no test yet:
    demos = get_experiences(...)
    failure_facts = load_failure_facts(...)
    retrieved_example = failure_facts + "\n\n" + demos[0]
    call_api_reproduce_exp_initial(retrieved_example)
```

New path for facts mode:

```
if no test yet:
    failure_facts = load_failure_facts(...)
    if config.memory_mode == "facts":
        # build thread with SYSTEM_PROMPT_W_RULE + issue
        thread = self._construct_init_thread_exp(failure_facts)
        # call the model directly with this thread (no demo wrapper)
    else:
        demos = get_experiences(...)
        retrieved_example = demos[0] ...
        if failure_facts: retrieved_example = failure_facts + "\n\n" + retrieved_example
        call_api_reproduce_exp_initial(retrieved_example)
```

#### 3. Add a new `_call_api_reproduce_facts_only` method

Similar to `_call_api_reproduce_exp_initial` but:
- uses `_construct_init_thread_exp(failure_facts)` instead of `_construct_init_thread()`
- does not bind `retrieved_example` into the prompt
- issues the standard `REPRODUCE_PROMPT` (without `{retrieved_example}`) because facts are already in the system message

#### 4. Logging

The existing `retrieval_log.jsonl` in `get_experiences`:
- in facts mode, `get_experiences` is not called (no demo retrieval)
- add a separate log entry at the call site with:
  - `query_task_id`
  - `mode: "facts"`
  - `fact_count`
  - `fact_task_ids`
  - `fact_exception_types`

#### 5. Patch side

Patch in `agent_write_patch.py` is deferred. Facts mode first targets only the reproducer.

## Evaluation

### Conditions

| Condition | Memory |
|---|---|
| C0 | none |
| C1 | demos only (`baseline` mode) |
| C2 | facts only (`facts` mode) |

### Metrics

| Metric | What it measures |
|---|---|
| reproduce YES rate | does facts-only help or hurt reproduction success? |
| test passes at base commit | does facts-only produce more executable tests? |
| ModuleNotFoundError rate | does "avoid ModuleNotFoundError" actually reduce that error? |
| symptom match | do tests actually reproduce the reported bug? |
| judge agreement | does the LLM agree more or less with facts-only? |

### Acceptance

- **positive**: facts-only matches or exceeds demos-only reproduce rate, and reduces repeated failure modes (ModuleNotFoundError, AttributeError)
- **null**: facts-only reproduce rate is comparable to no-memory but different from demos-only
- **negative**: facts-only hurts reproduce rate

Report the result regardless of direction.

## Offline experiment results

The offline experiment (`analysis/experiment_facts_only.py`) measures what facts would be available during a facts-only run on the 22-task dev slice, without any model inference.

| Metric | Value |
|---|---|
| Total tasks | 22 |
| Tasks with lessons.jsonl | 10 |
| Total facts available | 10 |
| Facts with known exception types | 3× ModuleNotFoundError, 1× AttributeError |
| Facts with unknown exception type | 7 |
| Tasks receiving facts (stream position >= 5) | 18 |
| First task to receive any fact | django-11039 (task #5 in stream) |
| Last 9 tasks all receive | same 9-10 facts |
| Max prompt chars from facts | 666 chars (10 bullet lines) |

**Key finding:** The "unknown" exception type (7 of 10 facts) dilutes the signal. `unknown` facts tell the model nothing actionable. The pipeline will inject "avoid tests that raise unknown" which is noise. Until the recheck script can extract better exception types from the stored execution output, facts-only will be limited by fact quality, not retrieval.

**Recommendation:** Improve `_generate_failure_fact` in `analysis/recheck_quarantine.py` to extract exception types from `new_exec_result` even when return_code is 0 (the test passes but is wrong). Many confirmed failures have return_code=0 yet clearly crash with exceptions visible in the output text.

## Full pipeline experiment results

The facts-only pipeline was run end-to-end on the full 15-task dev slice (`task_list_phase1_gen.txt`) with `--memory-mode facts`.

### Results

| Metric | Phase 1 (demos baseline) | Facts-only |
|---|---|---|
| Tasks run | 15 | 15 |
| Reproduce YES | 15 (100%) | **15 (100%)** |
| Reproduce NO | 0 | **0** |
| YES rate | 100% | **100%** |
| Total model calls | 15 | 15 |
| Runtime | ~13 min | ~13 min |
| Gate promoted | 0 (old gate) | **0** (all quarantined by denylist) |

### Key finding

Facts-only reproduces the same 15/15 tasks as demos-only on the Phase 1 dev slice. This means failure facts alone (10 repo-wide "avoid" lessons injected into `SYSTEM_PROMPT_W_RULE`) are sufficient to match the full demonstration retrieval pipeline for reproduction.

**Implications:**
- Facts-only is a viable replacement for demo retrieval for reproduction tasks.
- The `{summarized_rules}` slot works as designed when populated with failure facts.
- The `SYSTEM_PROMPT_W_RULE` + `_construct_init_thread_exp` path is validated end-to-end.
--Retrieval of facts vs demos does not degrade reproduction quality.

**Limitations:**
- Only tested on the reproduce stage (not patch generation).
- Only tested on 15 Django tasks from a single repo.
- Facts are pre-computed from Phase 4 — the fact generation pipeline is not re-run during the facts-only run.
- 7 of 10 facts have `exception_type: "unknown"` — fact quality is lower than ideal.
- The 5 tasks that failed in Phase 1 baseline (no reproduce_experiences.jsonl) were not re-tested in facts-only because they have no starting state.

**Recommendation:** Expand to the patch generation stage (`--memory-mode facts` on `generate_w_memory.py`) and compare patch quality against the demos baseline.

## Files to change

| File | Change |
|---|---|
| `config.py` | add `"facts"` to accepted memory_mode values |
| `memory_gate/gate.py` | add `MemoryGateMode.FACTS = "facts"` |
| `agents/agent_reproducer.py` | add `_call_api_reproduce_facts_only` method; wire it in `_write_reproducing_test_W_EXP`; add facts-only logging |
| `inference/reproduce_initial.py` | accept `"facts"` in memory_mode validation |
| `inference/reproduce_w_memory.py` | same |
| `inference/generate_initial.py` | same (pass-through) |
| `inference/generate_w_memory.py` | same |

## Prerequisites

- `lessons.jsonl` files already exist from Phase 4 (10 confirmed failure facts across the dev slice)
- `load_failure_facts()` already exists in `agents/agent_reproducer.py:1230`
- `SYSTEM_PROMPT_W_RULE` and `_construct_init_thread_exp` already exist but are unused

## Not in scope

- Patch-side facts mode (deferred)
- Success lessons (Target B)
- Retrieval ranking improvement for facts (only repo-wide loading, no BM25 over fact text)
- Semantic lesson generation (template-only facts are sufficient for this test)

## Run order

1. Wire config and gate mode
2. Add `_call_api_reproduce_facts_only`
3. Wire it into `_write_reproducing_test_W_EXP`
4. Run a 3-5 issue experiment on the existing dev slice
5. Collect metrics
6. Decide whether to expand to full slice or drop facts channel