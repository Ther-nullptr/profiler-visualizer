"""Static, paginated history figures built from the same validated ledger."""

from __future__ import annotations

import datetime as dt
import math
import unicodedata

import render_profile_breakdown as breakdown

WIDTH = 1600
MARGIN = 48
CONTENT = WIDTH - 2 * MARGIN
ROWS_PER_PAGE = 6


def wrapped(value, width, size=15):
    """Conservative wrapping also breaks long IDs and handles CJK labels."""
    lines = []
    for paragraph in str(value).splitlines() or [""]:
        line, used = "", 0.0
        for char in paragraph:
            factor = (
                1.0
                if unicodedata.east_asian_width(char) in ("W", "F") or char in "MW@#%"
                else 0.75
            )
            advance = size * factor
            if line and used + advance > width:
                split = line.rfind(" ")
                if split > len(line) // 2:
                    lines.append(line[:split])
                    line = line[split + 1 :]
                    used = sum(
                        size
                        * (
                            1.0
                            if unicodedata.east_asian_width(c) in ("W", "F")
                            or c in "MW@#%"
                            else 0.75
                        )
                        for c in line
                    )
                else:
                    lines.append(line)
                    line, used = "", 0.0
            line += char
            used += advance
        lines.append(line.rstrip())
    return lines


class Figure:
    def __init__(self):
        self.parts = []
        self.y = 44

    def text(self, x, y, value, *, size=15, weight=400, color="#25343d"):
        self.parts.append(
            breakdown._text(x, y, value, size=size, weight=weight, fill=color)
        )

    def paragraph(self, value, *, size=15, color="#53636e", width=CONTENT):
        for line in wrapped(value, width, size):
            self.text(MARGIN, self.y, line, size=size, color=color)
            self.y += size + 7

    def section(self, title):
        self.y += 18
        self.parts.append(
            f'<line x1="{MARGIN}" y1="{self.y}" x2="{WIDTH-MARGIN}" y2="{self.y}" stroke="#d5dee3"/>'
        )
        self.y += 32
        self.text(MARGIN, self.y, title, size=21, weight=700)
        self.y += 26

    def table(self, headings, rows, widths):
        assert sum(widths) == CONTENT
        for index, values in enumerate([headings, *rows]):
            cells = [
                wrapped(value, width - 24, 14) for value, width in zip(values, widths)
            ]
            height = max(len(lines) for lines in cells) * 20 + 20
            fill = "#e7eef1" if index == 0 else "#ffffff" if index % 2 else "#f0f4f6"
            self.parts.append(
                f'<rect x="{MARGIN}" y="{self.y}" width="{CONTENT}" height="{height}" fill="{fill}"/>'
            )
            x = MARGIN
            for lines, width in zip(cells, widths):
                for number, line in enumerate(lines):
                    color = (
                        "#b13753"
                        if line == "fail"
                        else "#157859" if line == "pass" else "#354651"
                    )
                    self.text(
                        x + 12,
                        self.y + 25 + number * 20,
                        line,
                        size=14,
                        weight=650 if index == 0 else 400,
                        color=color,
                    )
                x += width
            self.y += height

    def finish(self, title, generated_at):
        self.y += 30
        self.text(
            MARGIN,
            self.y,
            f"Generated {generated_at} | profile-visualizer | details and source fingerprints in companion report/manifest",
            size=12,
            color="#647581",
        )
        height = math.ceil(self.y + 30)
        svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}">',
            f"<title>{breakdown._escape(title)}</title>",
            '<style>text {font-family:"DejaVu Sans","Noto Sans CJK SC",sans-serif;letter-spacing:0}</style>',
            f'<rect width="{WIDTH}" height="{height}" fill="#f8fafb"/>',
            *self.parts,
            "</svg>",
        ]
        return "\n".join(svg), height


def render_pages(document, generated_at):
    states = {state["id"]: state for state in document["states"]}
    protocols = {protocol["id"]: protocol for protocol in document["protocols"]}
    all_runs = {run["id"]: run for run in document["runs"]}
    groups = list(
        dict.fromkeys(
            (run["protocol_id"], run["cohort_id"]) for run in document["runs"]
        )
    )
    edges = {
        (edge["candidate_run_id"], edge["kind"]): edge
        for edge in document["comparisons"]
    }
    output = []
    for protocol_id, cohort_id in groups:
        protocol = protocols[protocol_id]
        group_runs = sorted(
            (
                run
                for run in document["runs"]
                if (run["protocol_id"], run["cohort_id"]) == (protocol_id, cohort_id)
            ),
            key=lambda run: dt.datetime.fromisoformat(
                run["recorded_at"].replace("Z", "+00:00")
            ),
        )
        page_count = math.ceil(len(group_runs) / ROWS_PER_PAGE)
        maximum = max(run["value"] for run in group_runs)
        unit = protocol["metric"]["unit"]
        for start in range(0, len(group_runs), ROWS_PER_PAGE):
            runs = group_runs[start : start + ROWS_PER_PAGE]
            ids = {run["id"] for run in runs}
            focal = next(
                (run for run in runs if run["id"] == document["current_run_id"]),
                runs[-1],
            )
            state = states[focal["state_id"]]
            page_number = start // ROWS_PER_PAGE + 1
            figure = Figure()
            banner = (
                "MEASURED OPTIMIZATION HISTORY"
                if document["evidence_kind"] == "measured"
                else "SYNTHETIC FIXTURE - NOT PERFORMANCE EVIDENCE"
            )
            figure.paragraph(f"PROFILE VISUALIZER / {banner}", size=12)
            figure.y += 18
            figure.paragraph(document["title"], size=27, color="#1d303b")
            figure.y += 4
            figure.paragraph(protocol["label"], size=18)
            figure.paragraph(
                f"Cohort: {cohort_id} | {protocol['metric']['name']} ({unit}), {protocol['metric']['statistic']} | Page {page_number}/{page_count}",
                size=14,
            )
            figure.y += 10
            current_label = (
                "Designated current"
                if focal["id"] == document["current_run_id"]
                else "Page endpoint"
            )
            stats = [
                (current_label, state["label"]),
                ("Service time", f"{focal['value']:.3f} {unit}"),
            ]
            for kind, label in (
                ("incremental", "Incremental gain"),
                ("cumulative", "Versus original"),
                ("matched_precision", "Matched full precision"),
            ):
                edge = edges.get((focal["id"], kind))
                stats.append(
                    (label, f"{edge['speedup']:.3f}x" if edge else "Pending comparison")
                )
            cell_width = CONTENT / len(stats)
            stat_height = 0
            for index, (label, value) in enumerate(stats):
                x = MARGIN + index * cell_width
                figure.text(x, figure.y, label, size=13, color="#60727c")
                lines = wrapped(value, cell_width - 20, 20)
                for number, line in enumerate(lines):
                    figure.text(
                        x, figure.y + 29 + number * 25, line, size=20, weight=650
                    )
                stat_height = max(stat_height, 29 + len(lines) * 25)
            figure.y += stat_height

            figure.section("Measured service time")
            figure.paragraph(
                f"Bars share one scale in this cohort: 0 to {maximum:.3f} {unit}. Sample ranges are not confidence intervals.",
                size=13,
            )
            for run in runs:
                item = states[run["state_id"]]
                label = f"{item['label']} [{item['precision']}]"
                labels = wrapped(label, 315, 15)
                run_labels = wrapped(f"Run: {run['id']}", 850, 12)
                height = max(70, len(labels) * 21 + 29, 52 + len(run_labels) * 17)
                for index, line in enumerate(labels):
                    figure.text(
                        MARGIN, figure.y + 20 + 21 * index, line, size=15, weight=650
                    )
                figure.text(
                    MARGIN,
                    figure.y + height - 6,
                    f"{item['status']} / quality: {run['quality']['status']}",
                    size=12,
                    color=(
                        "#b13753" if run["quality"]["status"] == "fail" else "#657680"
                    ),
                )
                color = (
                    "#a84867"
                    if item["precision"].lower() in ("fp4", "w4a4")
                    else "#237da0" if "8" in item["precision"] else "#387665"
                )
                figure.parts.append(
                    f'<rect x="390" y="{figure.y + 4}" width="850" height="24" fill="#e1e8ec"/>'
                )
                figure.parts.append(
                    f'<rect x="390" y="{figure.y + 4}" width="{850 * run["value"] / maximum:.4f}" height="24" fill="{color}"/>'
                )
                figure.text(
                    1260,
                    figure.y + 24,
                    f"{run['value']:.3f} {unit}",
                    size=19,
                    weight=650,
                )
                for line_index, line in enumerate(run_labels):
                    figure.text(390, figure.y + 49 + 17 * line_index, line, size=12)
                figure.text(
                    1260,
                    figure.y + 49,
                    f"n={len(run['samples'])}; {run['min']:.3f}-{run['max']:.3f}",
                    size=12,
                )
                figure.y += height + 8

            figure.section("Explicit measured comparisons")
            selected_edges = [
                edge
                for edge in document["comparisons"]
                if edge["candidate_run_id"] in ids
            ]
            if selected_edges:
                rows = []
                for edge in selected_edges:
                    before = all_runs[edge["baseline_run_id"]]
                    after = all_runs[edge["candidate_run_id"]]
                    rows.append(
                        [
                            f"{edge['label']}\n{edge['kind']}",
                            edge["baseline_run_id"],
                            edge["candidate_run_id"],
                            f"{before['value']:.3f} -> {after['value']:.3f} {unit}",
                            f"{edge['saved']:+.3f} {unit}\n{edge['saved_percent']:+.2f}%",
                            f"{edge['speedup']:.3f}x",
                        ]
                    )
                figure.table(
                    [
                        "Change / comparison",
                        "Baseline run",
                        "Candidate run",
                        "Before -> after",
                        "Saved",
                        "Speedup",
                    ],
                    rows,
                    [320, 290, 290, 270, 200, 134],
                )
            else:
                figure.paragraph("No supported paired comparison on this page.")

            figure.section("Quality and numerical status")
            quality_rows = []
            for run in runs:
                item = states[run["state_id"]]
                quality = run["quality"]
                metric_text = (
                    "\n".join(
                        f"{metric['name']}: {metric['value']:.4g} {metric['unit']}"
                        for metric in quality["metrics"]
                    )
                    or "Not measured"
                )
                quality_rows.append(
                    [
                        item["label"],
                        f"{item['classification']}\n{item['status']}",
                        quality["status"],
                        quality["reference"] or "No assessed reference",
                        metric_text,
                    ]
                )
            figure.table(
                [
                    "Configuration",
                    "Change / adoption",
                    "Quality",
                    "Quality reference",
                    "Recorded metrics",
                ],
                quality_rows,
                [280, 230, 120, 414, 460],
            )

            observations = [
                [
                    states[run["state_id"]]["label"],
                    metric["name"],
                    f"{metric['value']:.6g}",
                    metric["unit"],
                ]
                for run in runs
                for metric in run["observations"]
            ]
            if observations:
                figure.section("Additional measurements")
                figure.table(
                    ["Configuration", "Metric", "Value", "Unit"],
                    observations,
                    [400, 604, 250, 250],
                )

            if document["optimizations"]:
                figure.section("Active optimization coverage")
                visible = list(dict.fromkeys(run["state_id"] for run in runs))
                widths = [400] + [(CONTENT - 400) // len(visible)] * len(visible)
                widths[-1] += CONTENT - sum(widths)
                coverage = []
                for optimization in document["optimizations"]:
                    row = [f"{optimization['label']}\n{optimization['scope']}"]
                    for key in visible:
                        active = states[key]["active_optimizations"]
                        row.append(
                            "Unknown"
                            if active is None
                            else "Yes" if optimization["id"] in active else "No"
                        )
                    coverage.append(row)
                figure.table(
                    [
                        "Optimization / scope",
                        *[states[key]["label"] for key in visible],
                    ],
                    coverage,
                    widths,
                )

            figure.section("Evidence boundaries")
            for note in (
                "Ratios use explicit measured pairs. Pending comparisons are not zero improvement, and historical ratios are not multiplied.",
                "Numerical classes are relative to the parent configuration. Exact fusion within FP4 does not make FP4 lossless versus BF16.",
                "Quality references can differ between rows. Adoption and quality are separate outcomes; full assessments and sources are in the manifest.",
            ):
                figure.paragraph(note, size=13)
            for note in document["notes"]:
                figure.paragraph("- " + note, size=12)
            svg, height = figure.finish(document["title"], generated_at)
            output.append(
                {
                    "protocol_id": protocol_id,
                    "cohort_id": cohort_id,
                    "run_ids": [run["id"] for run in runs],
                    "page": page_number,
                    "pages_in_cohort": page_count,
                    "width": WIDTH,
                    "height": height,
                    "svg": svg,
                }
            )
    return output
