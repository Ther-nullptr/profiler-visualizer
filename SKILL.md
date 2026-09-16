---
name: profile-visualizer
description: Render measured profiler breakdowns and PNG optimization-history figures with incremental/cumulative gains, precision coverage, quality status, and source provenance. Use after measured optimization or when reviewing historical gains; do not turn estimates into measured speedups.
---

# Profile Visualizer

Maintain one evidence workflow with two views: **component breakdown** for a
measured iteration and **optimization history** for an experiment campaign.
Keep the existing skill name and breakdown format; no separate ledger skill
is needed.

Read existing reports first. A request to visualize or summarize results does
not authorize new GPU runs, frequency changes, uploads, or a retrospective
benchmark campaign. Record missing comparisons as pending.

## Choose the View

- For a single profile or a before/after breakdown, use
  [input-schema.md](references/input-schema.md) and the existing SVG renderer.
- For cumulative progress, precision branches, or a historical dashboard, use
  [optimization-history.md](references/optimization-history.md). The ledger
  references the same breakdown JSON instead of duplicating component times.
- After a measured optimization in an established campaign, update both the
  affected breakdown and the project's ledger from that round's evidence.

For a new multi-iteration optimization campaign, start its project ledger with
the first supported snapshot, even if original-anchor comparisons are pending.
A one-off operator plot does not need a campaign ledger.

The skill owns recording, validation, and visualization. Numerical acceptance
and next-step optimization decisions belong to the experiment protocol, or
[lossless-first-optimization](../lossless-first-optimization/SKILL.md) when used.
Analytical Amdahl scenarios remain separate from measured history.

## Component Breakdown

1. Use an affected end-to-end profile under the comparison protocol. During an
   authorized optimization run, collect it before closing the measured iteration.
2. Normalize measured values, render the SVG, and inspect its labels and layout.
3. Link it from the report with the configuration and original profile sources.

If there is no comparable baseline, render a single snapshot without a speedup
claim. If a profile is missing, disclose that gap instead of inventing a
component distribution.

```bash
python3 ~/.codex/skills/profile-visualizer/scripts/render_profile_breakdown.py \
  profile-breakdown.json --output-dir docs/performance/figures
```

The existing command and schema remain backward compatible. It emits SVG,
Markdown, and a manifest with timestamp-first names.

## Optimization History

The unit of history is a **configuration state**, not just a Git commit.
Separate states, measurement runs, and explicit comparison edges. Store the
project ledger in the model repository, not inside the reusable skill.

Maintain the original reference, matched optimized full-precision reference,
and current configuration when measurements exist. Each comparison names its
actual baseline and candidate run. Compute differences and ratios directly;
never multiply ratios from separate rounds into a cumulative claim.

```bash
python3 ~/.codex/skills/profile-visualizer/scripts/render_optimization_history.py \
  docs/optimization/ledger.json --validate-only
python3 ~/.codex/skills/profile-visualizer/scripts/render_optimization_history.py \
  docs/optimization/ledger.json --output-dir docs/optimization/snapshots
```

The CLI defaults to **PNG**, with an editable SVG companion, Markdown summary,
and manifest. Each protocol/cohort is exported separately, paginated at six
runs per image. Show the generated PNG to the user; an HTML page is not required.
PNG rendering uses CairoSVG and the Cairo runtime, not browser screenshots or
generative image tools. If these dependencies are missing, report the requirement
rather than silently switching formats.

Use `--format html` for the optional interactive panel or `--format both` to
produce both formats. Add `--update-index` only to refresh `dashboard.md` for
PNG and/or `dashboard.html` for HTML. The default Python `render_file()` API
retains HTML compatibility; pass `output_format="png"` for direct API use.

Figures retain rejected/reverted measurements, numerical classes, quality
references and optimization coverage. Full configurations, quality assessments,
source links and component-profile references remain in the companion evidence.

When importing historical records, preserve unknown settings as unknown.
A recipe parent is not proof of measured improvement. Missing original-anchor
measurements stay pending. Select the designated current run explicitly,
rather than promoting the fastest candidate automatically.

## Evidence Contract

- Compare fixed workloads and declared intervention variables. Changing shape,
  hardware/power, workload, warmup, statistic, or timing boundary needs a separate
  protocol; comparison edges must also share a reviewed measurement cohort.
- For matched-precision gains, require the same known shared configuration and
  shared optimization coverage. A Decoder replacement is not just GEMM precision.
- Keep adoption status independent of quality. Numerical classes are relative to
  the parent; exact FP4 fusion does not make FP4 equivalent to BF16.
- Retain repeated samples and their spread; do not infer statistical confidence
  or quality acceptance from too few samples or a single proxy metric.
- Record only measured component times. Keep names stable and show unclassified
  time explicitly. The legacy breakdown renderer treats omitted categories as
  zero, so do not use omission to represent an unknown component.
- Do not add overlapping GPU durations into a wall-clock total. Keep profiled
  GPU work, clean service time, and arrival-to-visible latency separate.
- Incremental savings are conditional on the recorded parent. Without an
  isolated ablation, attribute a coupled change to the bundle, not each member.
- Preserve original reports and local raw sources. Track compact ledger JSON,
  reports, and diagrams; keep large traces, videos, and tensors local.

## Output and Review

Use `YYYYMMDD_HHMMSS_<name>_<artifact>` for every new snapshot, figure, report,
and manifest. Keep the timestamp first across different experiment names.
Use a fixed timestamp only for reproduction or tests. Do not rename historical
artifacts or silently overwrite a snapshot; history collisions receive a suffix.

Before citing output, verify its selected workload, precision, baseline IDs,
units, sample counts, numerical labels, quality reference, and active options.
Inspect PNG dimensions, nonblank pixels, labels and text layout before delivery.
For optional HTML changes, check desktop/mobile readability and embedded SVGs.
The manifest records normalized evidence and source digests.

A history-only refresh must not be reported as a new optimization experiment.
