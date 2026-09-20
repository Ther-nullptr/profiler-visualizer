# Contributing

Keep the renderers and evidence contract consistent. A formatting change must
not silently alter comparison eligibility, numerical labels, sample selection,
or the meanings of unknown and unmeasured values.

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Run scripts from the checkout. This is a source-distributed skill, not an
installed Python package; no `pip install -e .` step is required. Renderer code
must not import model repositories or depend on workstation-specific paths.

For a visual change, generate the examples, inspect the PNG/SVG, and check text
wrapping and image dimensions. For optional HTML changes, also exercise desktop
and mobile using `tests/check_history_browser.cjs` with local Playwright and
Chromium paths. Tests do not authorize model inference or frequency changes.

## Changes and Evidence

- Add focused regression tests for schema, comparison, or rendering changes.
- Preserve PNG as the history CLI default and the existing SVG breakdown API.
- Keep README commands consistent between English and Chinese.
- Label synthetic inputs prominently; never present them as performance evidence.
- Keep generated images/reports in `outputs/`, and raw experiments outside Git.
- Preserve source attribution and timestamp-first artifact names.
- Report checks actually run, including skipped or unavailable validation.

The project has no declared license at this extraction point. Do not add license
claims or remove existing attribution without a maintainer decision; see
[PROVENANCE.md](PROVENANCE.md).
