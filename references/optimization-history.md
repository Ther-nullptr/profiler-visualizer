# Optimization History

Use this mode to maintain cumulative progress and precision branches. The
existing [breakdown schema](input-schema.md) and SVG renderer remain unchanged.
The history renderer uses only the Python standard library and local assets.

## What the Panel Records

- **Protocol:** invariant workload, environment, and latency measurement boundary.
- **State:** a complete recipe, revision, numerical change, adoption status,
  actual enabled optimizations, and optional parent recipe.
- **Run:** repeated measured samples for a state under one protocol and cohort.
- **Comparison:** explicit baseline/candidate run IDs and a declared purpose.

States and runs are different: one commit can have multiple configurations,
and the same configuration may be measured in multiple sessions. Retain
rejected and reverted candidates without selecting them as current by default.

Each comparison must share a protocol and measurement cohort. A cohort is a
reviewed measurement window with compatible operating conditions, not an
arbitrary label assigned to all historical runs. Use a new cohort for a
revalidation session and rerun the necessary anchors there. Unknown operating
conditions do not establish comparability merely because two labels match.

Only deliberate intervention variables belong in the state. Put fixed model,
input/seed set, shape, output length/steps, KV initialization/window, hardware,
power/clocks, warmup, repetitions policy, and timing exclusions in the protocol.
For a streaming comparison also fix arrivals, deadlines, queue/drop policy and
visibility semantics. A jointly tuned policy is a separate scenario.

## Schema v1

The input is one JSON file, conventionally `docs/optimization/ledger.json`.
Larger campaigns may assemble it from per-run files before rendering. Keep
records immutable in Git; a new remeasurement gets a new run ID. Never replace
historical samples with the best observed repeat.

| Field | Contract |
|---|---|
| `schema_version` | Integer `1` |
| `title` | Non-empty display title |
| `evidence_kind` | `measured`; use `synthetic` only for fixtures/demonstrations |
| `current_run_id` | Explicit designated run; not automatically the fastest/latest |
| `protocols[]` | Unique `id`, `label`, `workload` object, `environment` object, `metric`; optional `original_state_id` |
| `metric` | `name`, latency `unit` (`s`, `ms`, `us`), `statistic` (`mean`, `median`) |
| `optimizations[]` | Unique `id`, `label`, `scope` (`shared`, `precision`) |
| `states[]` | Unique `id`, `label`, `revision`, `precision`, `classification`, `status`, `description`; optional `parent_id`, `shared_config`, `active_optimizations` |
| `runs[]` | Unique `id`, `state_id`, `protocol_id`, `cohort_id`, timezone-qualified `recorded_at` (defaults to `measured_at`), positive `samples[]`, non-empty `sources[]` |
| `comparisons[]` | Unique `id`, `label`, `kind`, `baseline_run_id`, `candidate_run_id` |
| `notes[]` | Context and evidence limitations |

`classification` describes the change relative to its parent: `reference`,
`exact`, `numerical_exception`, or `lossy`. An exact producer inside FP4 stays
part of a lossy FP4 model relative to BF16. `status` is independent:
`accepted`, `experimental`, `rejected`, or `reverted`.

`active_optimizations` is the actual enabled ID list. `null`/omitted means
unknown, while `[]` means known empty. `shared_config` captures all non-target
settings relevant to a fair precision comparison, including VAE/attention,
residual precision, compiler/fusion choices and numerical policy. Unknown
shared settings prevent a matched-precision claim, not recording the run.
Use JSON `null` for an unknown setting, including inside nested objects or
lists. Two equally unknown values are not a match. Use `false` or a named
disabled mode for a known disabled feature rather than overloading `null`.

`measured_at` may be omitted when the original record has no wall-clock time.
Use the report/import time as `recorded_at` and disclose its source. Do not
invent measurement timestamps while importing old artifacts. The panel orders
records by `recorded_at` and retains both fields in the evidence.

## Comparison Semantics

- `incremental`: baseline state must be the candidate state's recorded parent.
- `cumulative`: baseline state must match this protocol's `original_state_id`.
- `matched_precision`: baseline is BF16/FP16/W16A16; both states have the same
  known `shared_config` and the same enabled `shared` optimizations.

For every explicit edge:

```text
speedup = statistic(baseline samples) / statistic(candidate samples)
saved = statistic(baseline samples) - statistic(candidate samples)
```

The renderer never traverses a path multiplying ratios. An absent edge is
displayed as pending, even if ancestor states exist. Two rows with the same
commit/precision label are not an implicit comparison. The validator cannot
infer whether manually declared configs/cohorts reflect actual execution;
review their source evidence before registering an edge.

Incremental savings are order-dependent. Without an isolated ablation,
attribute multiple simultaneous changes to their bundle. Runtime/GPU overlap
also prevents blindly adding component deltas into end-to-end savings.

## Optional Run Evidence

`quality` defaults to `{"status": "unmeasured"}`. An assessed `pass` or `fail`
requires `reference`, `assessment` (protocol/threshold and scope), and a
non-empty `sources` list. Optional `metrics` are objects with `name`, finite
`value`, and `unit`. Keep reference and dataset visible; the renderer does not
compare unrelated DINO scores or compute a synthetic combined quality score.

`observations` uses the same metric objects for measured memory, p50/p95/p99,
deadline miss rate, drops or backlog. Their protocol must state the timing
and denominator. These values are shown as evidence, not mixed into the
latency ratio. This first version does not infer a quality/latency Pareto front.

`profile` optionally references an existing normalized breakdown JSON:

```json
{"path": "../performance/current_wall_input.json", "name": "Current"}
```

Paths resolve relative to the ledger. `name` must exactly match one entry in
`profiles[]`. The same SVG renderer embeds that entry with its own metric
boundary; a GPU profile does not replace clean end-to-end samples. Missing
local profiles produce a visible warning; malformed profiles or unknown names
are errors. Missing individual components must not be represented as zero.
`--validate-only` performs these profile checks too, without rendering images
or creating output files.

## Minimal Example

These numbers are a synthetic fixture, **not a measured model speedup**.

```json
{
  "schema_version": 1,
  "title": "Synthetic history example",
  "evidence_kind": "synthetic",
  "current_run_id": "after-run",
  "protocols": [{
    "id": "fixed", "label": "Fixed test workload", "original_state_id": "before",
    "workload": {"model": "fixture", "input": "fixed", "warmup": "excluded"},
    "environment": {"device": "fixture", "operating_conditions": "fixed"},
    "metric": {"name": "Complete service", "unit": "ms", "statistic": "mean"}
  }],
  "optimizations": [{"id": "fusion", "label": "Fusion", "scope": "shared"}],
  "states": [{
    "id": "before", "label": "Original", "revision": "fixture-v0", "precision": "bf16",
    "classification": "reference", "status": "accepted", "description": "Original fixture",
    "shared_config": {"decoder": "original"}, "active_optimizations": []
  }, {
    "id": "after", "parent_id": "before", "label": "Fused", "revision": "fixture-v1", "precision": "bf16",
    "classification": "exact", "status": "accepted", "description": "One fixture change",
    "shared_config": {"decoder": "original"}, "active_optimizations": ["fusion"]
  }],
  "runs": [{
    "id": "before-run", "state_id": "before", "protocol_id": "fixed", "cohort_id": "fixture-session",
    "measured_at": "2026-09-15T10:00:00+08:00", "samples": [99, 101], "sources": ["synthetic fixture"]
  }, {
    "id": "after-run", "state_id": "after", "protocol_id": "fixed", "cohort_id": "fixture-session",
    "measured_at": "2026-09-15T10:01:00+08:00", "samples": [79, 81], "sources": ["synthetic fixture"]
  }],
  "comparisons": [{
    "id": "step", "label": "Apply fusion", "kind": "incremental",
    "baseline_run_id": "before-run", "candidate_run_id": "after-run"
  }, {
    "id": "total", "label": "Versus original", "kind": "cumulative",
    "baseline_run_id": "before-run", "candidate_run_id": "after-run"
  }]
}
```

## Update and Review

After an authorized measured iteration, register the configuration, repeats,
quality status and explicit comparisons; then validate and render using the
commands in `SKILL.md`. Import existing machine-readable summaries rather
than extracting rounded numbers from prose. If raw repeats are unavailable,
link the historical report as unresolved rather than fabricating repetitions.

The panel groups protocols/cohorts, displays absolute-time history and paired
savings, preserves numerical/adoption/quality labels, shows enabled-optimization
coverage, and links detailed configuration/source/profile evidence. It does not
claim causal Shapley attribution or automatically promote a candidate.

Outputs are timestamp-first HTML, Markdown and manifest snapshots. Repeated
timestamps receive collision suffixes. `--update-index` additionally refreshes
generated `dashboard.html`; leave it off to preserve an existing page.
Raw profiles and videos remain outside the tracked ledger.

The manifest fingerprints the ledger bytes, referenced normalized profiles,
and local timing/quality sources up to 32 MiB each. Larger raw files are marked
`not_hashed_large`; missing sources are `unavailable`, remote links are
`external_not_fetched`, and concurrent source changes are flagged. This avoids
scanning multi-gigabyte traces during a panel refresh. Fingerprints identify
the referenced evidence version; they do not verify that arbitrary source
formats semantically agree with the manually registered samples or thresholds.

Each HTML ratio exposes its baseline run ID. The measured-comparisons table
and expandable records retain all comparison types, including cumulative and
matched-precision edges. The page links its manifest and Markdown report.

An optional browser smoke check is available at `tests/check_history_browser.cjs`
in the skills repository. Provide an installed Playwright module through
`PLAYWRIGHT_MODULE`, a compatible browser through `CHROMIUM_PATH`, then pass
the generated HTML path and a local screenshot directory. It checks desktop,
mobile, cohort switching, evidence links, and embedded profiles without running
model inference or downloading dependencies.
