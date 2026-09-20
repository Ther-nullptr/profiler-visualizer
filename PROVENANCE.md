# Provenance

## Source Snapshot

- Original repository: `git@github.com:BBuf/AI-Infra-Auto-Driven-SKILLS.git`
- Original prefix: `skills/profile-visualizer/`
- Source commit: `4f8642ce99634f76c02d968dabc02d7f994b4cc9`
- Extraction date: 2026-09-20
- Raw extracted history tip: `90ee31f19f7256deb5004500dbfd5c89cfcdc367`
- Identity-corrected history tip: `df668661f879eb07b5c52edd35d6add0decacf94`

The source includes locally developed commits. Its source commit ID does not
imply that this revision has been pushed to the original GitHub repository.

The standalone history was created with:

```bash
git subtree split --prefix=skills/profile-visualizer --quiet 4f8642ce99634f76c02d968dabc02d7f994b4cc9
```

The five relevant commits retain their contents, dates, and messages. Their IDs
change because paths and parent history have been restricted to this skill.
No unrelated model code, raw traces, or repository-wide history was imported.
The original working tree and its branch history remain intact.

Before the first publication, the maintainer corrected the imported commits'
author and committer identity to `ther-nullptr <1329438302@qq.com>`.
Every corrected commit has the same content tree as its raw extracted counterpart.
Only unpublished commits in this standalone repository were corrected; the
original repository's history was not rewritten.

| Original commit | Raw extracted commit | Identity-corrected commit | Change |
|---|---|---|---|
| `45ed401` | `59bfa67` | `eb29139` | Initial timestamped SVG breakdown |
| `9e7aaf6` | `2c1f573` | `f6a6523` | Optional optimization-workflow coordination |
| `069fb4d` | `3b1d3cf` | `ebb78b0` | Timestamp-first filenames and Markdown |
| `17d5257` | `102b872` | `819e986` | Optimization-history accounting and HTML |
| `4f8642c` | `90ee31f` | `df66866` | Default PNG history output |

## Standalone Integration

Four test files were imported separately from the same original source commit:
`test_profile_visualizer.py`, `test_optimization_history.py`,
`test_profile_history_png.py`, and `check_history_browser.cjs` under `tests/`.
Their path assumptions were adapted to the repository root.

The extraction adds bilingual project documentation, dependency declarations,
self-contained synthetic examples, and independent-checkout tests. It removes
the required relative documentation link to a sibling skill. The core renderer,
history validator, and assets retain the imported implementation.

This repository's GitHub slug is `profiler-visualizer`. Its skill identifier is
still `profile-visualizer`; the different spelling is intentional compatibility,
not a second implementation.

## Licensing Status

No LICENSE or COPYING file was present in the original source snapshot.
This extraction does not infer a license from public repository visibility and
does not add a license grant. Project licensing remains undeclared pending an
explicit maintainer decision. Source history and the maintainer-requested
identity correction are documented above.
