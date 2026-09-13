---
name: profile-visualizer
description: Render measured profiler component breakdowns as timestamped SVG reports with before/after comparisons, optimization annotations, and source provenance. Use after performance optimization or when comparing profile runs; do not use inferred timings as measured data.
---

# Profile Visualizer

Turn the latest comparable profile evidence into an auditable visual artifact.

For a campaign that prioritizes exact optimizations before quantization, use
[lossless-first-optimization](../lossless-first-optimization/SKILL.md) to manage
component eligibility, numerical exceptions, iteration decisions and Amdahl
headroom. This skill remains responsible for measured breakdown rendering;
analytical headroom belongs in a separate, explicitly labeled artifact.

## Completion Rule

After each optimization iteration that changes measured performance:

1. Re-profile the affected end-to-end workload under the same protocol as the
   comparison run.
2. Normalize the measured component times using
   [references/input-schema.md](references/input-schema.md).
3. Render the report with the bundled script.
4. Inspect the SVG and link it from the optimization report beside the raw
   profile sources.

Do not call an optimization iteration complete while its current breakdown is
missing. If a comparable baseline is unavailable, render a one-profile snapshot
and state that no speedup claim is supported.

## Render

```bash
python3 skills/profile-visualizer/scripts/render_profile_breakdown.py \
  profile-breakdown.json \
  --output-dir docs/performance/figures
```

The renderer writes:

- `YYYYMMDD_HHMMSS_<prefix>_profile_breakdown.svg`
- `YYYYMMDD_HHMMSS_<prefix>_profile_breakdown.md`
- `YYYYMMDD_HHMMSS_<prefix>_profile_breakdown.manifest.json`

Put the local timestamp first in every newly generated figure, companion report
and manifest filename, so sorting works across different experiment names.
Use the same convention for campaign-level reports, for example
`YYYYMMDD_HHMMSS_fp8_scale_report.md`. A stable index may link to these reports.
Do not rename published historical artifacts or break their existing links.

The local timestamp is mandatory and lexicographically sortable. The manifest
records the normalized input, source digest, renderer version, and generated
filename. Use `--timestamp` only to reproduce an existing artifact or in tests;
do not reuse an old timestamp for a new measurement.

## Evidence Contract

- Put only measured values in `profiles[].components`; never backfill a category
  with an Amdahl-law estimate or a theoretical kernel speedup.
- Compare runs only when model, input shape, warmup, repetition statistic,
  clocks/power mode, precision scope, and measurement boundary are compatible.
- Include profile files, benchmark summaries, or trace paths in `sources`.
- Make the first profile the baseline and the last profile the current result.
- Keep component names stable across iterations so colors and rows remain
  comparable. The renderer unions missing components and displays them as zero.
- Account for the full measured total. A small unclassified remainder is shown
  explicitly as `Unattributed`; component sums above the declared total are an
  error.
- Describe concrete implemented changes in `optimizations`, including the
  affected components and measured impact. Keep rejected experiments in the
  written report, not in the list of active optimizations.

## Review Gate

Before citing the figure, verify:

- the SVG title, workload metadata, units, profile totals, and optimization text
  match the raw artifacts;
- the current profile is actually the latest successful run;
- the timestamp-first SVG, report and manifest are tracked or intentionally stored with
  the benchmark artifacts;
- the written performance claim uses end-to-end speedup when the figure uses an
  end-to-end denominator, and kernel-only speedup when it uses a kernel boundary.
