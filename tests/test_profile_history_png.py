import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

from test_optimization_history import ledger, write_ledger
from optimization_history import HistoryError, normalize_history
import render_optimization_history as renderer
from history_figure import ROWS_PER_PAGE, render_pages, wrapped


def test_cli_defaults_to_png_without_html(tmp_path, capsys):
    pytest.importorskip("cairosvg")
    from PIL import Image

    source = write_ledger(tmp_path)
    assert renderer.main([str(source), "--png-scale", "0.5", "--update-index"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert "html" not in result
    assert not list(tmp_path.glob("*.html"))
    assert Path(result["index"]).name == "dashboard.md"
    with Image.open(result["png"]) as picture:
        assert picture.format == "PNG"
        assert picture.width == 800
        assert picture.height > 100
        assert any(low < 200 and high > 240 for low, high in picture.getextrema()[:3])
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["output_format"] == "png"
    assert manifest["output_html"] is None
    assert manifest["png_backend"]["name"] == "CairoSVG"
    assert manifest["normalized_input"]["current_run_id"] == "fp8"
    assert Path(result["png"]).name in Path(result["report"]).read_text()


def test_png_pages_separate_cohorts_and_preserve_all_runs(tmp_path):
    pytest.importorskip("cairosvg")
    source = ledger()
    for index in range(4):
        source["runs"].append(dict(source["runs"][0], id=f"extra-{index}"))
    source["runs"].append(dict(source["runs"][0], id="other-cohort", cohort_id="other"))
    source["current_run_id"] = "other-cohort"
    result = renderer.render_file(
        write_ledger(tmp_path, source), tmp_path, output_format="png", png_scale=0.3
    )
    manifest = json.loads(Path(result["manifest"]).read_text())
    pages = manifest["figure_outputs"]
    assert len(pages) == 3
    assert all(len(page["run_ids"]) <= ROWS_PER_PAGE for page in pages)
    assert {run for page in pages for run in page["run_ids"]} == {
        run["id"] for run in source["runs"]
    }
    assert all(
        page["cohort_id"] == "other"
        for page in pages
        if "other-cohort" in page["run_ids"]
    )
    assert result["png"] == next(
        page["png"] for page in pages if "other-cohort" in page["run_ids"]
    )
    assert len(set(result["pngs"])) == 3
    assert all(
        Path(path).name.startswith(Path(result["report"]).stem + "_p")
        for path in result["pngs"]
    )


def test_static_figure_keeps_pending_comparisons_quality_and_baseline_ids():
    source = ledger()
    source["comparisons"] = [
        edge for edge in source["comparisons"] if edge["kind"] != "cumulative"
    ]
    page = render_pages(normalize_history(source), "fixed")[0]
    root = ET.fromstring(page["svg"])
    text = " ".join(root.itertext())
    assert "Pending comparison" in text
    assert "SYNTHETIC FIXTURE" in text
    assert "synthetic original" in text
    assert "common" in text and "fp8" in text
    assert "rejected / quality: fail" in text
    assert "matched_precision" in text
    assert "2.000x" not in text


def test_png_collision_does_not_overwrite_remaining_image(tmp_path):
    pytest.importorskip("cairosvg")
    source = write_ledger(tmp_path)
    kwargs = dict(
        output_format="png", png_scale=0.25, prefix="case", timestamp="20260916_120000"
    )
    first = renderer.render_file(source, tmp_path, **kwargs)
    image = Path(first["png"]).read_bytes()
    for key in ("report", "manifest"):
        Path(first[key]).unlink()
    for path in first["svgs"]:
        Path(path).unlink()
    second = renderer.render_file(source, tmp_path, **kwargs)
    assert (
        Path(second["png"]).name == "20260916_120000_case_optimization_history_01.png"
    )
    assert Path(first["png"]).read_bytes() == image


def test_both_formats_are_explicit_and_keep_separate_indexes(tmp_path):
    pytest.importorskip("cairosvg")
    result = renderer.render_file(
        write_ledger(tmp_path),
        tmp_path,
        output_format="both",
        png_scale=0.25,
        update_index=True,
    )
    assert Path(result["html"]).is_file()
    assert Path(result["png"]).is_file()
    assert Path(result["index"]).name == "dashboard.md"
    assert Path(result["html_index"]).name == "dashboard.html"


@pytest.mark.parametrize("scale", [0, -1, 4, float("nan"), float("inf"), True, "large"])
def test_invalid_png_scale_is_rejected_without_creating_output(tmp_path, scale):
    source = write_ledger(tmp_path)
    output = tmp_path / "output"
    with pytest.raises(HistoryError, match="png_scale"):
        renderer.render_file(source, output, output_format="png", png_scale=scale)
    assert not output.exists()


def test_missing_png_dependency_is_reported_but_html_still_works(tmp_path, monkeypatch):
    source = write_ledger(tmp_path)
    output = tmp_path / "output"
    monkeypatch.setitem(sys.modules, "cairosvg", None)
    with pytest.raises(HistoryError, match="PNG output requires CairoSVG"):
        renderer.render_file(source, output, output_format="png")
    assert not output.exists()
    assert Path(
        renderer.render_file(source, output, output_format="html")["html"]
    ).is_file()


def test_heading_spacing_and_long_identifier_wrapping():
    page = render_pages(normalize_history(ledger()), "fixed")[0]
    root = ET.fromstring(page["svg"])
    text = root.findall(".//{http://www.w3.org/2000/svg}text")
    banner, title = text[:2]
    assert (
        float(title.attrib["y"]) - float(title.attrib["font-size"])
        > float(banner.attrib["y"]) + 2
    )
    identifier = "W" * 150
    lines = wrapped(identifier, 300)
    assert "".join(lines) == identifier
    assert max(map(len, lines)) * 15 <= 300


def test_long_label_escapes_svg_and_is_not_dropped():
    source = ledger()
    source["title"] = "Measured <history> & comparison"
    source["states"][0]["label"] = "W" * 100
    source["notes"] = ["Evidence gap: " + "x" * 400]
    page = render_pages(normalize_history(source), "fixed")[0]
    root = ET.fromstring(page["svg"])
    assert "Measured <history> & comparison" in " ".join(root.itertext())
    assert page["height"] > 0
