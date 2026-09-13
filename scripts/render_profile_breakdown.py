#!/usr/bin/env python3
"""Render an auditable, timestamped profiler breakdown as self-contained SVG."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import math
import re
import sys
import textwrap
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
RENDERER_VERSION = "1.1.0"
TIMESTAMP_RE = re.compile(r"^\d{8}_\d{6}$")


class InputError(ValueError):
    """Raised when the normalized profile input is internally inconsistent."""


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{path} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise InputError(f"{path} must be a list")
    return [_nonempty_string(item, f"{path}[{index}]") for index, item in enumerate(value)]


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{path} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise InputError(f"{path} must be finite and non-negative")
    return result


def normalize_document(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise InputError("top-level input must be a JSON object")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise InputError(f"schema_version must be {SCHEMA_VERSION}")

    title = _nonempty_string(raw.get("title"), "title")
    subtitle = raw.get("subtitle", "")
    if subtitle:
        subtitle = _nonempty_string(subtitle, "subtitle")

    metric_raw = raw.get("metric")
    if not isinstance(metric_raw, dict):
        raise InputError("metric must be an object")
    metric = {
        "name": _nonempty_string(metric_raw.get("name"), "metric.name"),
        "unit": _nonempty_string(metric_raw.get("unit"), "metric.unit"),
        "aggregation": _nonempty_string(metric_raw.get("aggregation"), "metric.aggregation"),
        "lower_is_better": metric_raw.get("lower_is_better", True),
    }
    if not isinstance(metric["lower_is_better"], bool):
        raise InputError("metric.lower_is_better must be a boolean")

    context_raw = raw.get("context", {})
    if not isinstance(context_raw, dict):
        raise InputError("context must be an object")
    context: dict[str, str] = {}
    for key, value in context_raw.items():
        context[_nonempty_string(key, "context key")] = _nonempty_string(
            value, f"context.{key}"
        )

    profiles_raw = raw.get("profiles")
    if not isinstance(profiles_raw, list) or not 1 <= len(profiles_raw) <= 4:
        raise InputError("profiles must contain one to four entries")

    profiles: list[dict[str, Any]] = []
    profile_names: set[str] = set()
    component_names: set[str] = set()
    for profile_index, profile_raw in enumerate(profiles_raw):
        path = f"profiles[{profile_index}]"
        if not isinstance(profile_raw, dict):
            raise InputError(f"{path} must be an object")
        name = _nonempty_string(profile_raw.get("name"), f"{path}.name")
        if name in profile_names:
            raise InputError(f"duplicate profile name: {name}")
        profile_names.add(name)

        components_raw = profile_raw.get("components")
        if not isinstance(components_raw, list) or not components_raw:
            raise InputError(f"{path}.components must be a non-empty list")
        components: list[dict[str, Any]] = []
        local_names: set[str] = set()
        for component_index, component_raw in enumerate(components_raw):
            component_path = f"{path}.components[{component_index}]"
            if not isinstance(component_raw, dict):
                raise InputError(f"{component_path} must be an object")
            component_name = _nonempty_string(
                component_raw.get("name"), f"{component_path}.name"
            )
            if component_name in local_names:
                raise InputError(f"duplicate component in {name}: {component_name}")
            local_names.add(component_name)
            component_names.add(component_name)
            components.append(
                {
                    "name": component_name,
                    "value": _number(component_raw.get("value"), f"{component_path}.value"),
                }
            )

        component_sum = sum(component["value"] for component in components)
        total_raw = profile_raw.get("total")
        total = component_sum if total_raw is None else _number(total_raw, f"{path}.total")
        tolerance = max(1e-6, total * 0.005)
        if component_sum > total + tolerance:
            raise InputError(
                f"{path} component sum {component_sum:g} exceeds total {total:g} "
                f"beyond tolerance {tolerance:g}"
            )
        if component_sum > total:
            total = component_sum
        elif total - component_sum > 1e-9:
            components.append({"name": "Unattributed", "value": total - component_sum})
            component_names.add("Unattributed")
        profiles.append({"name": name, "total": total, "components": components})

    optimizations_raw = raw.get("optimizations", [])
    if not isinstance(optimizations_raw, list):
        raise InputError("optimizations must be a list")
    optimizations: list[dict[str, Any]] = []
    for index, optimization_raw in enumerate(optimizations_raw):
        path = f"optimizations[{index}]"
        if not isinstance(optimization_raw, dict):
            raise InputError(f"{path} must be an object")
        components = _string_list(optimization_raw.get("components", []), f"{path}.components")
        unknown = sorted(set(components) - component_names)
        if unknown:
            raise InputError(f"{path}.components contains unknown names: {', '.join(unknown)}")
        optimizations.append(
            {
                "name": _nonempty_string(optimization_raw.get("name"), f"{path}.name"),
                "description": _nonempty_string(
                    optimization_raw.get("description"), f"{path}.description"
                ),
                "impact": _nonempty_string(optimization_raw.get("impact"), f"{path}.impact"),
                "components": components,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "title": title,
        "subtitle": subtitle,
        "metric": metric,
        "context": context,
        "profiles": profiles,
        "optimizations": optimizations,
        "notes": _string_list(raw.get("notes", []), "notes"),
        "sources": _string_list(raw.get("sources", []), "sources"),
    }


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "profile"


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _fmt(value: float) -> str:
    if value >= 1000:
        return f"{value:,.1f}"
    if value >= 100:
        return f"{value:.1f}"
    if value >= 10:
        return f"{value:.2f}"
    return f"{value:.3f}"


def _component_color(name: str) -> str:
    if name == "Unattributed":
        return "#B8C0C8"
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    hue = int.from_bytes(digest[:2], "big") % 360
    saturation = 54 + digest[2] % 18
    lightness = 42 + digest[3] % 12
    return f"hsl({hue} {saturation}% {lightness}%)"


def _component_order(document: dict[str, Any]) -> list[str]:
    latest = {item["name"]: item["value"] for item in document["profiles"][-1]["components"]}
    maximum: dict[str, float] = {}
    for profile in document["profiles"]:
        for component in profile["components"]:
            maximum[component["name"]] = max(maximum.get(component["name"], 0.0), component["value"])
    return sorted(maximum, key=lambda name: (-latest.get(name, 0.0), -maximum[name], name.lower()))


def _wrap(value: str, width: int) -> list[str]:
    return textwrap.wrap(value, width=width, break_long_words=False, break_on_hyphens=False) or [""]


def _text(
    x: float,
    y: float,
    value: Any,
    *,
    size: int = 18,
    weight: int = 400,
    fill: str = "#16212B",
    anchor: str = "start",
    css_class: str = "",
) -> str:
    class_attr = f' class="{_escape(css_class)}"' if css_class else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}"{class_attr}>{_escape(value)}</text>'
    )


def _multiline(
    x: float,
    y: float,
    lines: Iterable[str],
    *,
    size: int = 17,
    line_height: int = 24,
    fill: str = "#33424F",
    weight: int = 400,
) -> tuple[list[str], float]:
    output: list[str] = []
    current_y = y
    for line in lines:
        output.append(_text(x, current_y, line, size=size, weight=weight, fill=fill))
        current_y += line_height
    return output, current_y


def render_svg(document: dict[str, Any], generated_at: str, timestamp: str) -> str:
    width = 1600
    margin = 72
    chart_x = 360
    chart_width = width - chart_x - margin
    unit = document["metric"]["unit"]
    profiles = document["profiles"]
    order = _component_order(document)
    max_total = max(profile["total"] for profile in profiles) or 1.0
    component_maps = [
        {component["name"]: component["value"] for component in profile["components"]}
        for profile in profiles
    ]

    context_line = "  |  ".join(f"{key}: {value}" for key, value in document["context"].items())
    context_lines = _wrap(context_line, 135) if context_line else []
    subtitle_lines = _wrap(document["subtitle"], 120) if document["subtitle"] else []
    header_height = 150 + 27 * (len(subtitle_lines) + len(context_lines))
    chart_height = 74 + 82 * len(profiles)
    table_height = 74 + 43 * len(order)

    optimization_line_counts = []
    for optimization in document["optimizations"]:
        body = f'{optimization["description"]} Impact: {optimization["impact"]}'
        optimization_line_counts.append(len(_wrap(body, 125)))
    optimization_height = 0
    if optimization_line_counts:
        optimization_height = 70 + sum(38 + 23 * count for count in optimization_line_counts)

    note_line_count = sum(len(_wrap(note, 132)) for note in document["notes"])
    source_line_count = sum(len(_wrap(source, 132)) for source in document["sources"])
    provenance_height = 0
    if note_line_count or source_line_count:
        provenance_height = 78 + 24 * (note_line_count + source_line_count)
        if note_line_count and source_line_count:
            provenance_height += 28

    height = header_height + chart_height + table_height + optimization_height + provenance_height + 105
    svg: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">'
        ),
        f'<title id="title">{_escape(document["title"])}</title>',
        (
            f'<desc id="desc">Timestamped profiler component breakdown generated at '
            f'{_escape(generated_at)}.</desc>'
        ),
        "<style>",
        "text { font-family: Inter, 'Noto Sans', 'Noto Sans CJK SC', Arial, sans-serif; letter-spacing: 0; }",
        ".mono { font-family: 'JetBrains Mono', 'Noto Sans Mono', monospace; }",
        "</style>",
        f'<rect width="{width}" height="{height}" fill="#F7F9FA"/>',
        f'<rect x="0" y="0" width="14" height="{height}" fill="#138A72"/>',
        _text(margin, 72, document["title"], size=34, weight=700),
        _text(width - margin, 68, timestamp, size=17, weight=600, fill="#53616D", anchor="end", css_class="mono"),
        _text(width - margin, 94, generated_at, size=14, fill="#71808C", anchor="end"),
    ]

    y = 110.0
    if subtitle_lines:
        lines, y = _multiline(margin, y, subtitle_lines, size=19, line_height=27, fill="#43515D")
        svg.extend(lines)
    metric_summary = (
        f'{document["metric"]["name"]} ({unit})  |  '
        f'{document["metric"]["aggregation"]}'
    )
    svg.append(_text(margin, y + 5, metric_summary, size=16, weight=600, fill="#138A72"))
    y += 34
    if context_lines:
        lines, y = _multiline(margin, y, context_lines, size=15, line_height=23, fill="#64727E")
        svg.extend(lines)
    y = max(y + 24, float(header_height))

    svg.append(_text(margin, y, "Measured breakdown", size=23, weight=700))
    svg.append(_text(width - margin, y, f"Scale: 0 to {_fmt(max_total)} {unit}", size=15, fill="#71808C", anchor="end"))
    y += 34
    for profile_index, profile in enumerate(profiles):
        row_y = y + profile_index * 82
        profile_total = profile["total"]
        svg.append(_text(margin, row_y + 20, profile["name"], size=17, weight=650))
        ratio = "baseline"
        baseline_total = profiles[0]["total"]
        if profile_index:
            if document["metric"]["lower_is_better"]:
                ratio_value = baseline_total / profile_total if profile_total else math.inf
            else:
                ratio_value = profile_total / baseline_total if baseline_total else math.inf
            ratio = f"{ratio_value:.3f}x vs baseline" if math.isfinite(ratio_value) else "infinite vs baseline"
        svg.append(
            _text(
                margin,
                row_y + 45,
                f'{_fmt(profile_total)} {unit}  |  {ratio}',
                size=14,
                fill="#64727E",
            )
        )
        svg.append(
            f'<rect x="{chart_x}" y="{row_y}" width="{chart_width}" height="50" rx="4" fill="#E4E9EC"/>'
        )
        cursor = float(chart_x)
        for component_name in order:
            value = component_maps[profile_index].get(component_name, 0.0)
            segment_width = chart_width * value / max_total
            if segment_width <= 0:
                continue
            color = _component_color(component_name)
            svg.append(
                f'<rect x="{cursor:.2f}" y="{row_y}" width="{segment_width:.2f}" height="50" fill="{color}">'
                f'<title>{_escape(component_name)}: {_fmt(value)} {_escape(unit)}</title></rect>'
            )
            if segment_width >= 92:
                svg.append(
                    _text(
                        cursor + segment_width / 2,
                        row_y + 31,
                        f"{value / profile_total * 100:.1f}%" if profile_total else "0%",
                        size=13,
                        weight=700,
                        fill="#FFFFFF",
                        anchor="middle",
                    )
                )
            cursor += segment_width
        svg.append(
            f'<line x1="{chart_x}" y1="{row_y + 58}" x2="{chart_x + chart_width}" '
            'y2="{:.1f}" stroke="#C9D1D7" stroke-width="1"/>'.format(row_y + 58)
        )
    y += 82 * len(profiles) + 30

    svg.append(_text(margin, y, "Components", size=23, weight=700))
    y += 36
    component_column_width = 480
    delta_width = 180 if len(profiles) > 1 else 0
    profile_column_width = (width - 2 * margin - component_column_width - delta_width) / len(profiles)
    svg.append(_text(margin, y, "Component", size=14, weight=700, fill="#53616D"))
    for index, profile in enumerate(profiles):
        x = margin + component_column_width + profile_column_width * (index + 0.5)
        svg.append(_text(x, y, profile["name"], size=13, weight=700, fill="#53616D", anchor="middle"))
    if len(profiles) > 1:
        svg.append(_text(width - margin, y, "Current - baseline", size=13, weight=700, fill="#53616D", anchor="end"))
    y += 17
    svg.append(f'<line x1="{margin}" y1="{y}" x2="{width - margin}" y2="{y}" stroke="#AEB9C1" stroke-width="1.5"/>')

    optimization_numbers: dict[str, list[int]] = {}
    for number, optimization in enumerate(document["optimizations"], start=1):
        for component_name in optimization["components"]:
            optimization_numbers.setdefault(component_name, []).append(number)

    baseline_map = component_maps[0]
    current_map = component_maps[-1]
    for row_index, component_name in enumerate(order):
        row_y = y + 31 + row_index * 43
        if row_index % 2:
            svg.append(f'<rect x="{margin}" y="{row_y - 27}" width="{width - 2 * margin}" height="42" fill="#EEF2F4"/>')
        color = _component_color(component_name)
        svg.append(f'<rect x="{margin}" y="{row_y - 15}" width="13" height="13" rx="2" fill="{color}"/>')
        markers = optimization_numbers.get(component_name, [])
        marker_text = f"  [{','.join(str(number) for number in markers)}]" if markers else ""
        svg.append(_text(margin + 23, row_y - 3, component_name + marker_text, size=15, weight=550))
        for profile_index, profile in enumerate(profiles):
            value = component_maps[profile_index].get(component_name, 0.0)
            share = value / profile["total"] * 100 if profile["total"] else 0.0
            x = margin + component_column_width + profile_column_width * (profile_index + 0.5)
            svg.append(
                _text(
                    x,
                    row_y - 3,
                    f"{_fmt(value)} {unit}  ({share:.1f}%)",
                    size=14,
                    fill="#33424F",
                    anchor="middle",
                    css_class="mono",
                )
            )
        if len(profiles) > 1:
            before = baseline_map.get(component_name, 0.0)
            after = current_map.get(component_name, 0.0)
            delta = after - before
            percent = delta / before * 100 if before else 0.0
            delta_text = f"{delta:+.2f} {unit}  ({percent:+.1f}%)" if before else f"{delta:+.2f} {unit}"
            delta_color = "#187B62" if delta < 0 else "#B54747" if delta > 0 else "#64727E"
            svg.append(_text(width - margin, row_y - 3, delta_text, size=14, weight=650, fill=delta_color, anchor="end", css_class="mono"))
    y += 43 * len(order) + 42

    if document["optimizations"]:
        svg.append(_text(margin, y, "Implemented optimizations", size=23, weight=700))
        y += 34
        for number, optimization in enumerate(document["optimizations"], start=1):
            svg.append(f'<circle cx="{margin + 14}" cy="{y + 2}" r="14" fill="#138A72"/>')
            svg.append(_text(margin + 14, y + 7, number, size=14, weight=750, fill="#FFFFFF", anchor="middle"))
            svg.append(_text(margin + 40, y + 6, optimization["name"], size=17, weight=700))
            y += 29
            body = f'{optimization["description"]} Impact: {optimization["impact"]}'
            lines, y = _multiline(margin + 40, y, _wrap(body, 125), size=15, line_height=23, fill="#43515D")
            svg.extend(lines)
            if optimization["components"]:
                affected = "Affected: " + ", ".join(optimization["components"])
                svg.append(_text(margin + 40, y, affected, size=13, weight=600, fill="#138A72"))
                y += 21
            y += 15

    if document["notes"] or document["sources"]:
        svg.append(f'<line x1="{margin}" y1="{y}" x2="{width - margin}" y2="{y}" stroke="#C9D1D7" stroke-width="1"/>')
        y += 36
    if document["notes"]:
        svg.append(_text(margin, y, "Notes", size=18, weight=700))
        y += 27
        for note in document["notes"]:
            lines = _wrap("- " + note, 132)
            rendered, y = _multiline(margin, y, lines, size=14, line_height=22, fill="#53616D")
            svg.extend(rendered)
        y += 14
    if document["sources"]:
        svg.append(_text(margin, y, "Profile sources", size=18, weight=700))
        y += 27
        for source in document["sources"]:
            lines = _wrap("- " + source, 132)
            rendered, y = _multiline(margin, y, lines, size=13, line_height=21, fill="#53616D")
            svg.extend(rendered)

    svg.append(_text(margin, height - 35, f"profile-visualizer v{RENDERER_VERSION}", size=13, fill="#71808C"))
    svg.append(_text(width - margin, height - 35, "Measured values only", size=13, weight=650, fill="#138A72", anchor="end"))
    svg.append("</svg>")
    return "\n".join(svg) + "\n"


def render_markdown(document: dict[str, Any], generated_at: str, svg_name: str) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")

    metric = document["metric"]
    profiles = document["profiles"]
    lines = [f"# {document['title']}", "", f"Generated: {generated_at}", "",
             f"Metric: {metric['name']} ({metric['unit']}); {metric['aggregation']}.", "",
             f"![Measured breakdown]({svg_name})", "",
             "| Component | " + " | ".join(cell(p["name"]) for p in profiles) + " |",
             "|---|" + "---:|" * len(profiles)]
    names = list(dict.fromkeys(c["name"] for p in profiles for c in p["components"]))
    for name in names:
        values = [next((c["value"] for c in p["components"] if c["name"] == name), 0.0) for p in profiles]
        lines.append(f"| {cell(name)} | " + " | ".join(f"{v:.6g}" for v in values) + " |")
    lines += ["| Total | " + " | ".join(f"{p['total']:.6g}" for p in profiles) + " |", ""]
    if document["optimizations"]:
        lines += ["## Implemented Optimizations", ""]
        for opt in document["optimizations"]:
            lines.append(f"- {opt['name']}: {opt['description']} Impact: {opt['impact']}")
    for title, key in (("Notes", "notes"), ("Sources", "sources")):
        if document[key]:
            lines += ["", f"## {title}", ""] + [f"- {value}" for value in document[key]]
    return "\n".join(lines) + "\n"


def _timestamp_value(value: str | None) -> tuple[str, str]:
    if value is None:
        current = dt.datetime.now().astimezone()
    else:
        if not TIMESTAMP_RE.fullmatch(value):
            raise InputError("--timestamp must use YYYYMMDD_HHMMSS")
        local_zone = dt.datetime.now().astimezone().tzinfo
        current = dt.datetime.strptime(value, "%Y%m%d_%H%M%S").replace(tzinfo=local_zone)
    return current.strftime("%Y%m%d_%H%M%S"), current.isoformat(timespec="seconds")


def _available_stem(output_dir: Path, base_stem: str, overwrite: bool) -> str:
    if overwrite:
        return base_stem
    stem = base_stem
    collision = 0
    while any((output_dir / f"{stem}{suffix}").exists() for suffix in (".svg", ".manifest.json", ".md")):
        collision += 1
        stem = f"{base_stem}_{collision:02d}"
    return stem


def render_file(
    input_path: Path,
    output_dir: Path,
    *,
    prefix: str | None = None,
    timestamp: str | None = None,
    overwrite: bool = False,
) -> dict[str, str]:
    input_bytes = input_path.read_bytes()
    try:
        raw = json.loads(input_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InputError(f"cannot parse {input_path}: {error}") from error
    document = normalize_document(raw)
    timestamp_value, generated_at = _timestamp_value(timestamp)
    output_dir.mkdir(parents=True, exist_ok=True)
    chosen_prefix = _slug(prefix or document["title"])
    stem = _available_stem(
        output_dir,
        f"{timestamp_value}_{chosen_prefix}_profile_breakdown",
        overwrite,
    )
    svg_path = output_dir / f"{stem}.svg"
    manifest_path = output_dir / f"{stem}.manifest.json"
    report_path = output_dir / f"{stem}.md"

    svg_path.write_text(render_svg(document, generated_at, timestamp_value), encoding="utf-8")
    report_path.write_text(render_markdown(document, generated_at, svg_path.name), encoding="utf-8")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "renderer_version": RENDERER_VERSION,
        "generated_at": generated_at,
        "timestamp": timestamp_value,
        "input_path": str(input_path.resolve()),
        "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "output_svg": str(svg_path.resolve()),
        "output_report": str(report_path.resolve()),
        "normalized_input": document,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"svg": str(svg_path.resolve()), "manifest": str(manifest_path.resolve()), "report": str(report_path.resolve())}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="normalized profile breakdown JSON")
    parser.add_argument("--output-dir", type=Path, default=None, help="artifact directory; defaults to the input directory")
    parser.add_argument("--prefix", help="descriptive name after the timestamp; defaults to a slug of the title")
    parser.add_argument("--timestamp", help="fixed YYYYMMDD_HHMMSS timestamp for reproduction or tests")
    parser.add_argument("--overwrite", action="store_true", help="overwrite an artifact with the same timestamp")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = render_file(
            args.input,
            args.output_dir or args.input.parent,
            prefix=args.prefix,
            timestamp=args.timestamp,
            overwrite=args.overwrite,
        )
    except (InputError, OSError) as error:
        print(f"profile-visualizer: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
