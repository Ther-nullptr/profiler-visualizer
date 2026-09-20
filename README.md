# Profile Visualizer

[English](README.md) | [简体中文](README.zh-CN.md)

A standalone agent skill and visualization toolkit for measured inference
performance. Render profiler breakdowns and track optimization history without
mixing incompatible baselines or treating estimates as measurements.

The GitHub repository is named **profiler-visualizer**. The skill name and
installation directory remain **profile-visualizer** for compatibility.

## Features

- PNG optimization-history figures, with editable SVG and evidence manifests.
- Per-iteration SVG component breakdowns with optimization annotations.
- Explicit incremental, cumulative, and matched-precision comparisons.
- Quality/adoption status, optimization coverage, and source fingerprints.
- Optional offline HTML view; no model weights, GPU, or inference engine required.

## Quick Start

Python 3.10+ is required; validation uses Python 3.12 on Linux/aarch64.
PNG export needs CairoSVG and the system Cairo runtime. SVG breakdowns and
optional HTML generation do not require CairoSVG.

```bash
git clone https://github.com/Ther-nullptr/profiler-visualizer.git profile-visualizer
cd profile-visualizer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/render_optimization_history.py examples/history.json --output-dir outputs/demo
```

The example uses **synthetic data, not measured model performance**. Its PNG,
SVG, Markdown, and manifest filenames start with a timestamp. Each workload
and measurement cohort is rendered separately.

Validate input or select another view:

```bash
python scripts/render_optimization_history.py examples/history.json --validate-only
python scripts/render_optimization_history.py examples/history.json --format html --output-dir outputs/html
python scripts/render_profile_breakdown.py examples/profile.json --output-dir outputs/breakdown
```

Use `--format both` for PNG and HTML together. `--update-index` also refreshes
`dashboard.md` and/or `dashboard.html`; timestamped snapshots remain intact.
If CairoSVG cannot load, install the Cairo runtime for your OS before exporting
PNG. There is no need to install or change PyTorch.

## Install as a Skill

The repository root is the skill directory. From this checkout:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$PWD" "${CODEX_HOME:-$HOME/.codex}/skills/profile-visualizer"
```

Check an existing installation before replacing it; the command intentionally
does not force an overwrite. Invoke `$profile-visualizer` in your next agent
turn. Scripts can also run directly without an agent or sibling skills.

## Documentation

| Path | Purpose |
|---|---|
| [SKILL.md](SKILL.md) | Agent workflow and evidence rules |
| [Breakdown schema](references/input-schema.md) | Component-time input and SVG export |
| [History schema](references/optimization-history.md) | States, runs, comparisons, PNG and HTML output |
| `scripts/` | Validation, comparison accounting, and renderers |
| `assets/` | Optional HTML styles and interactions |
| `examples/` | Small, self-contained synthetic inputs |
| `tests/` | Accounting, rendering, provenance, and portability checks |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development and validation |

Missing comparisons stay pending. Cumulative gains require an explicit
original-anchor measurement; historical speedup ratios are never multiplied.
Full-precision parity also requires known matching shared configuration and
optimization coverage. Raw traces, videos, and generated outputs stay outside Git.

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests require no GPU or model repository. Optional browser checks are documented
in the history guide and are not needed for PNG export.

## Provenance and Licensing

Extracted from `AI-Infra-Auto-Driven-SKILLS/skills/profile-visualizer`, retaining
its relevant commit history and source provenance. See [PROVENANCE.md](PROVENANCE.md).
No LICENSE file was present in the source snapshot; this extraction does not
add or imply a license grant. Project licensing awaits an explicit maintainer declaration.
