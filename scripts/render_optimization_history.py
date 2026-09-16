#!/usr/bin/env python3
"""Render a validated optimization ledger as an offline HTML dashboard."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote, urlsplit

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import render_profile_breakdown as breakdown
from optimization_history import HistoryError, load_history

RENDERER_VERSION = "1.0.0"
ASSETS = SCRIPT_DIR.parent / "assets"
MAX_SOURCE_HASH_BYTES = 32 * 1024 * 1024


def escape(value):
    return html.escape(str(value), quote=True)


def fmt(value):
    return f"{value:,.3f}" if value is not None else "Not measured"


def sources_html(sources, input_dir, output_dir):
    links = []
    for source in sources:
        parts = urlsplit(source)
        href = None
        if parts.scheme in ("http", "https") and parts.netloc:
            href = source
        elif not parts.scheme and not parts.netloc:
            local = (input_dir / source).expanduser().resolve()
            if local.is_file():
                href = quote(os.path.relpath(local, output_dir), safe="/")
        label = escape(source)
        links.append(
            f'<li><a href="{escape(href)}">{label}</a></li>'
            if href
            else f"<li>{label}</li>"
        )
    return '<ul class="sources">' + "".join(links) + "</ul>"


def metric_list(items):
    if not items:
        return '<span class="muted">Not measured</span>'
    return (
        "<dl>"
        + "".join(
            f"<dt>{escape(item['name'])}</dt><dd>{fmt(item['value'])} {escape(item['unit'])}</dd>"
            for item in items
        )
        + "</dl>"
    )


def fingerprint_sources(document, input_dir):
    references = {}
    for run in document["runs"]:
        for role, values in (
            ("timing", run["sources"]),
            ("quality", run["quality"]["sources"]),
        ):
            for source in values:
                references.setdefault(source, []).append(
                    {"run_id": run["id"], "role": role}
                )
    result = []
    for source, uses in references.items():
        item = {"source": source, "uses": uses, "status": "unavailable"}
        try:
            parsed = urlsplit(source)
            if parsed.scheme or parsed.netloc:
                item["status"] = "external_not_fetched"
            else:
                path = (input_dir / source).expanduser().resolve()
                item["path"] = str(path)
                if path.is_file():
                    before = path.stat()
                    item["size_bytes"] = before.st_size
                    if before.st_size > MAX_SOURCE_HASH_BYTES:
                        item["status"] = "not_hashed_large"
                    else:
                        digest = hashlib.sha256()
                        with path.open("rb") as handle:
                            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                                digest.update(chunk)
                        after = path.stat()
                        if (before.st_size, before.st_mtime_ns) != (
                            after.st_size,
                            after.st_mtime_ns,
                        ):
                            item["status"] = "changed_during_read"
                        else:
                            item.update(status="hashed", sha256=digest.hexdigest())
        except (OSError, ValueError) as error:
            item.update(status="unavailable", error=str(error))
        result.append(item)
    return result


def load_profiles(document, input_dir, generated_at, timestamp, *, render_images=True):
    images, provenance, warnings = {}, [], []
    cache = {}
    for run in document["runs"]:
        reference = run["profile"]
        if reference is None:
            continue
        path = (input_dir / reference["path"]).expanduser().resolve()
        if not path.is_file():
            warnings.append(f"{run['id']}: profile unavailable: {path}")
            continue
        if path not in cache:
            content = path.read_bytes()
            try:
                profile = breakdown.normalize_document(json.loads(content))
            except (ValueError, UnicodeDecodeError) as error:
                raise HistoryError(f"invalid profile {path}: {error}") from error
            cache[path] = profile
            provenance.append(
                {"path": str(path), "sha256": hashlib.sha256(content).hexdigest()}
            )
        profile = cache[path]
        selected = next(
            (item for item in profile["profiles"] if item["name"] == reference["name"]),
            None,
        )
        if selected is None:
            raise HistoryError(
                f"{run['id']}: unknown profile name {reference['name']!r}"
            )
        if not render_images:
            continue
        # Reuse the existing component renderer; never substitute GPU work for service time.
        single = dict(profile, profiles=[selected], optimizations=[])
        svg = breakdown.render_svg(single, generated_at, timestamp)
        image = base64.b64encode(svg.encode()).decode()
        images[run["id"]] = (
            f'<p class="boundary">{escape(profile["metric"]["name"])} / '
            f'{escape(profile["metric"]["aggregation"])} / {escape(profile["metric"]["unit"])}</p>'
            f'<img class="breakdown" src="data:image/svg+xml;base64,{image}" '
            f'alt="{escape(selected["name"])} measured component breakdown">'
        )
    return images, provenance, warnings


def comparison_cell(comparison):
    if comparison is None:
        return '<span class="muted">Pending comparison</span>'
    return (
        f'<span class="comparison" title="{escape(comparison["label"])}">'
        f'{comparison["speedup"]:.3f}x<small>baseline: '
        f'{escape(comparison["baseline_run_id"])}</small></span>'
    )


def render_page(document, group, index, images, input_dir, output_dir):
    states = {item["id"]: item for item in document["states"]}
    protocol = next(p for p in document["protocols"] if p["id"] == group[0])
    runs = [r for r in document["runs"] if (r["protocol_id"], r["cohort_id"]) == group]
    runs.sort(
        key=lambda r: dt.datetime.fromisoformat(r["recorded_at"].replace("Z", "+00:00"))
    )
    run_ids = {r["id"] for r in runs}
    run_index = {r["id"]: r for r in runs}
    dom_ids = {r["id"]: f"record-{index}-{i}" for i, r in enumerate(runs)}
    edges = [c for c in document["comparisons"] if c["candidate_run_id"] in run_ids]
    by_candidate = {(c["candidate_run_id"], c["kind"]): c for c in edges}
    focal = next((r for r in runs if r["id"] == document["current_run_id"]), runs[-1])
    unit = escape(protocol["metric"]["unit"])
    maximum = max(r["value"] for r in runs)
    state = states[focal["state_id"]]
    original = comparison_cell(by_candidate.get((focal["id"], "cumulative")))
    matched = comparison_cell(by_candidate.get((focal["id"], "matched_precision")))
    focus_label = (
        "Designated current run"
        if focal["id"] == document["current_run_id"]
        else "Latest recorded run"
    )
    parts = [
        f'<article class="cohort" data-cohort="{index}">',
        f'<section><h2>{escape(protocol["label"])}</h2>',
        f'<p class="boundary">{escape(group[1])} / {escape(protocol["metric"]["name"])} / '
        f'{escape(protocol["metric"]["statistic"])} ({unit})</p>',
        '<div class="summary">',
        f'<div><span>{focus_label}</span><strong>{escape(state["label"])}</strong></div>',
        f'<div><span>Service time</span><strong>{fmt(focal["value"])} {unit}</strong></div>',
        f"<div><span>Versus original</span><strong>{original}</strong></div>",
        f"<div><span>Matched full precision</span><strong>{matched}</strong></div>",
        f'<div><span>Adoption / quality</span><strong>{escape(state["status"])} / '
        f'{escape(focal["quality"]["status"])}</strong></div></div></section>',
        '<section><h2>Measured history</h2><div class="history-bars">',
    ]
    for run in runs:
        state = states[run["state_id"]]
        width = run["value"] / maximum * 100
        precision = state["precision"].lower()
        color = (
            "#a84867"
            if precision in ("fp4", "w4a4")
            else "#237da0" if "8" in precision else "#387665"
        )
        parts.append(
            f'<div class="history-row"><a href="#{dom_ids[run["id"]]}">{escape(state["label"])}</a>'
            f'<div class="track" aria-label="{escape(state["label"])}: {fmt(run["value"])} {unit}">'
            f'<span style="width:{width:.6f}%;background:{color}"></span></div>'
            f'<strong>{fmt(run["value"])} {unit}</strong>'
            f'<small>n={len(run["samples"])} / {escape(state["status"])}</small></div>'
        )
    parts += [
        '</div><div class="table-scroll"><table><thead><tr><th>Configuration / parent</th>',
        "<th>Precision</th><th>Numerical change</th><th>Time / sample range</th>",
        "<th>Incremental</th><th>Cumulative</th><th>Matched precision</th><th>Quality</th>",
        "</tr></thead><tbody>",
    ]
    for run in runs:
        state = states[run["state_id"]]
        parent = (
            states[state["parent_id"]]["label"]
            if state["parent_id"]
            else "No recorded parent"
        )
        quality = run["quality"]["status"]
        parts.append(
            f'<tr><td><a href="#{dom_ids[run["id"]]}">{escape(state["label"])}</a><small>{escape(parent)}</small></td>'
            f'<td>{escape(state["precision"])}</td><td>{escape(state["classification"])}</td>'
            f'<td>{fmt(run["value"])} {unit}<small>{fmt(run["min"])} - {fmt(run["max"])}</small></td>'
            + "".join(
                f'<td>{comparison_cell(by_candidate.get((run["id"], kind)))}</td>'
                for kind in ("incremental", "cumulative", "matched_precision")
            )
            + f'<td class="quality-{quality}">{quality}</td></tr>'
        )
    parts += [
        "</tbody></table></div></section>",
        "<section><h2>Measured comparisons</h2>",
    ]
    if edges:
        parts.append(
            '<div class="table-scroll"><table><thead><tr><th>Change</th><th>Measured pair</th>'
            "<th>Before</th><th>After</th><th>Saved</th><th>Speedup</th></tr></thead><tbody>"
        )
        for edge in edges:
            baseline = run_index[edge["baseline_run_id"]]
            current = run_index[edge["candidate_run_id"]]
            color = "saving" if edge["saved"] > 0 else "regression"
            parts.append(
                f'<tr><td>{escape(edge["label"])}<small>{edge["kind"]}</small></td><td>{escape(edge["baseline_run_id"])} &rarr; '
                f'{escape(edge["candidate_run_id"])}</td><td>{fmt(baseline["value"])} {unit}</td>'
                f'<td>{fmt(current["value"])} {unit}</td><td class="{color}">{edge["saved"]:+.3f} {unit} '
                f'({edge["saved_percent"]:+.2f}%)</td><td>{edge["speedup"]:.3f}x</td></tr>'
            )
        parts.append("</tbody></table></div>")
    else:
        parts.append('<p class="muted">No explicit paired measurement.</p>')
    parts.append("</section>")

    if document["optimizations"]:
        visible_states = list(dict.fromkeys(r["state_id"] for r in runs))
        parts += [
            '<section><h2>Active optimization coverage</h2><div class="table-scroll"><table><thead>',
            "<tr><th>Optimization</th><th>Scope</th>",
        ]
        parts.extend(
            f'<th>{escape(states[key]["label"])}</th>' for key in visible_states
        )
        parts.append("</tr></thead><tbody>")
        for opt in document["optimizations"]:
            parts.append(f'<tr><td>{escape(opt["label"])}</td><td>{opt["scope"]}</td>')
            for key in visible_states:
                active = states[key]["active_optimizations"]
                value = (
                    "Unknown"
                    if active is None
                    else "Yes" if opt["id"] in active else "No"
                )
                parts.append(f'<td class="coverage-{value.lower()}">{value}</td>')
            parts.append("</tr>")
        parts.append("</tbody></table></div></section>")

    parts += ["<section><h2>Evidence and component profiles</h2>"]
    for run in runs:
        state = states[run["state_id"]]
        quality = run["quality"]
        details = {
            "run_id": run["id"],
            "measured_at": run["measured_at"],
            "recorded_at": run["recorded_at"],
            "state": state,
            "samples": run["samples"],
            "sample_std": run["std"],
            "comparisons": [
                edge for edge in edges if edge["candidate_run_id"] == run["id"]
            ],
        }
        parts += [
            f'<details id="{dom_ids[run["id"]]}"><summary>{escape(state["label"])} '
            f'<span>{escape(state["status"])} / quality: {quality["status"]}</span></summary>',
            '<div class="evidence"><div><h3>Quality</h3>',
            f'<p class="quality-{quality["status"]}">{quality["status"]}</p>',
            f'<p>{escape(quality["reference"] or "No assessed reference")}</p>',
            metric_list(quality["metrics"]),
            f'<p>{escape(quality["assessment"] or "")}</p>',
            sources_html(quality["sources"], input_dir, output_dir),
            "</div><div><h3>Additional measurements</h3>",
            metric_list(run["observations"]),
            "<h3>Sources</h3>",
            sources_html(run["sources"], input_dir, output_dir),
            "</div></div>",
            images.get(
                run["id"], '<p class="muted">No available component profile.</p>'
            ),
            f"<pre>{escape(json.dumps(details, indent=2, ensure_ascii=False))}</pre></details>",
        ]
    parts += [
        "</section><section><h2>Protocol</h2>",
        f"<pre>{escape(json.dumps(protocol, indent=2, ensure_ascii=False))}</pre></section></article>",
    ]
    return "\n".join(parts)


def render_html(document, images, generated_at, input_dir, output_dir):
    groups = list(
        dict.fromkeys((r["protocol_id"], r["cohort_id"]) for r in document["runs"])
    )
    current = next(r for r in document["runs"] if r["id"] == document["current_run_id"])
    selected = groups.index((current["protocol_id"], current["cohort_id"]))
    protocols = {p["id"]: p for p in document["protocols"]}
    options = "".join(
        f'<option value="{index}"{" selected" if index == selected else ""}>'
        f'{escape(protocols[group[0]]["label"])} / {escape(group[1])}</option>'
        for index, group in enumerate(groups)
    )
    pages = "\n".join(
        render_page(document, group, i, images, input_dir, output_dir)
        for i, group in enumerate(groups)
    )
    badge = (
        "MEASURED HISTORY"
        if document["evidence_kind"] == "measured"
        else "SYNTHETIC FIXTURE / NOT PERFORMANCE EVIDENCE"
    )
    notes = "".join(f"<li>{escape(note)}</li>" for note in document["notes"])
    css = (ASSETS / "history.css").read_text()
    script = (ASSETS / "history.js").read_text()
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(document['title'])}</title><style>{css}</style></head><body>
<header><div><p class="eyebrow">PROFILE VISUALIZER / {badge}</p><h1>{escape(document['title'])}</h1></div>
<label for="cohort">Workload / measurement cohort<select id="cohort">{options}</select></label></header>
<main>{pages}<section><h2>Measurement notes</h2><ul>{notes}</ul>
<p>Ratios use explicit measured pairs, not products of historical speedups. Savings are conditional on the recorded parent configuration.</p>
<p>Numerical labels describe each change relative to its parent. An exact change within FP4 does not make FP4 lossless relative to BF16.</p>
<p>Component profiles retain their own timing boundaries; GPU work is not substituted for end-to-end latency.</p>
</section></main><footer>Generated {escape(generated_at)} / profile-visualizer history v{RENDERER_VERSION}</footer>
<script>{script}</script></body></html>
"""


def render_markdown(document, generated_at, html_name):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")

    states = {s["id"]: s for s in document["states"]}
    protocols = {p["id"]: p for p in document["protocols"]}
    lines = [
        f"# {document['title']}",
        "",
        f"Generated: {generated_at}",
        "",
        f"Evidence: **{document['evidence_kind']}**. [Dashboard]({html_name}).",
        "",
        "| Run | Protocol / cohort | Configuration | Time | n | Adoption | Quality |",
        "|---|---|---|---:|---:|---|---|",
    ]
    for run in document["runs"]:
        state = states[run["state_id"]]
        unit = protocols[run["protocol_id"]]["metric"]["unit"]
        lines.append(
            f"| {cell(run['id'])} | {cell(run['protocol_id'])} / {cell(run['cohort_id'])} | "
            f"{cell(state['label'])} | {run['value']:.6g} {unit} | {len(run['samples'])} | "
            f"{state['status']} | {run['quality']['status']} |"
        )
    lines += [
        "",
        "## Explicit Comparisons",
        "",
        "| Kind | Baseline | Candidate | Speedup | Saved (protocol unit) |",
        "|---|---|---|---:|---:|",
    ]
    for edge in document["comparisons"]:
        lines.append(
            f"| {edge['kind']} | {cell(edge['baseline_run_id'])} | {cell(edge['candidate_run_id'])} | "
            f"{edge['speedup']:.6g}x | {edge['saved']:+.6g} |"
        )
    lines += [
        "",
        "Missing comparison edges are pending, not zero improvement. Ratios are never multiplied across rounds.",
        "Numerical classifications are relative to the parent; adoption and quality are separate fields.",
        "",
        "## Notes",
        "",
    ]
    lines.extend(f"- {note}" for note in document["notes"])
    lines += ["", "## Sources", ""]
    lines.extend(
        f"- {source}"
        for source in dict.fromkeys(s for r in document["runs"] for s in r["sources"])
    )
    return "\n".join(lines) + "\n"


def render_file(
    input_path, output_dir, *, prefix=None, timestamp=None, update_index=False
):
    input_bytes = input_path.read_bytes()
    document = load_history(input_path, content=input_bytes)
    timestamp_value, generated_at = breakdown._timestamp_value(timestamp)
    output_dir = output_dir.resolve()
    images, profile_sources, warnings = load_profiles(
        document, input_path.resolve().parent, generated_at, timestamp_value
    )
    document["notes"].extend(warnings)
    source_evidence = fingerprint_sources(document, input_path.resolve().parent)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = f"{timestamp_value}_{breakdown._slug(prefix or document['title'])}_optimization_history"
    stem, collision = base, 0
    while any(
        (output_dir / f"{stem}{suffix}").exists()
        for suffix in (".html", ".md", ".manifest.json")
    ):
        collision += 1
        stem = f"{base}_{collision:02d}"
    html_path, report_path, manifest_path = (
        output_dir / f"{stem}{suffix}" for suffix in (".html", ".md", ".manifest.json")
    )
    page = render_html(
        document, images, generated_at, input_path.resolve().parent, output_dir
    )
    provenance_link = (
        f'<p><a href="{escape(manifest_path.name)}">Evidence manifest</a> / '
        f'<a href="{escape(report_path.name)}">Markdown report</a></p>'
    )
    page = page.replace("</footer>", provenance_link + "</footer>", 1)
    html_path.write_text(page, encoding="utf-8")
    report_path.write_text(
        render_markdown(document, generated_at, html_path.name), encoding="utf-8"
    )
    manifest = {
        "renderer_version": RENDERER_VERSION,
        "generated_at": generated_at,
        "timestamp": timestamp_value,
        "input_path": str(input_path.resolve()),
        "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "profile_sources": profile_sources,
        "source_evidence": source_evidence,
        "normalized_input": document,
        "output_html": str(html_path),
        "output_report": str(report_path),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    result = {
        "html": str(html_path),
        "report": str(report_path),
        "manifest": str(manifest_path),
    }
    if update_index:
        index = output_dir / "dashboard.html"
        index.write_text(page, encoding="utf-8")
        result["index"] = str(index)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="optimization history JSON")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--prefix")
    parser.add_argument("--timestamp", help="YYYYMMDD_HHMMSS, for reproduction/tests")
    parser.add_argument(
        "--update-index",
        action="store_true",
        help="also replace generated dashboard.html",
    )
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.validate_only:
            document = load_history(args.input)
            _, profile_sources, warnings = load_profiles(
                document, args.input.resolve().parent, "", "", render_images=False
            )
            result = {
                "valid": True,
                "runs": len(document["runs"]),
                "comparisons": len(document["comparisons"]),
                "profile_sources": profile_sources,
                "warnings": warnings,
            }
        else:
            result = render_file(
                args.input,
                args.output_dir or args.input.parent,
                prefix=args.prefix,
                timestamp=args.timestamp,
                update_index=args.update_index,
            )
    except (HistoryError, breakdown.InputError, OSError) as error:
        print(f"profile-visualizer history: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
