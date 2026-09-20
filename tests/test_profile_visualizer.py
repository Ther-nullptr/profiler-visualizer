import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "render_profile_breakdown.py"
SPEC = importlib.util.spec_from_file_location("render_profile_breakdown", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _document():
    return {
        "schema_version": 1,
        "title": "VAE <steady> decode",
        "subtitle": "fixed workload",
        "metric": {
            "name": "GPU time",
            "unit": "ms",
            "aggregation": "median",
            "lower_is_better": True,
        },
        "context": {"hardware": "Thor"},
        "profiles": [
            {
                "name": "Before",
                "total": 10.0,
                "components": [
                    {"name": "Convolution", "value": 6.0},
                    {"name": "Pointwise", "value": 3.0},
                ],
            },
            {
                "name": "Current",
                "total": 6.0,
                "components": [
                    {"name": "Convolution", "value": 3.0},
                    {"name": "Pointwise", "value": 2.5},
                ],
            },
        ],
        "optimizations": [
            {
                "name": "Vectorize chunks",
                "description": "Decode steady chunks in one call.",
                "impact": "1.67x end-to-end",
                "components": ["Convolution", "Pointwise"],
            }
        ],
        "sources": ["trace.nsys-rep"],
    }


def test_render_writes_timestamped_svg_and_manifest(tmp_path):
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(_document()), encoding="utf-8")

    result = MODULE.render_file(
        input_path,
        tmp_path,
        prefix="vae",
        timestamp="20260902_130405",
    )

    svg_path = Path(result["svg"])
    manifest_path = Path(result["manifest"])
    assert svg_path.name == "20260902_130405_vae_profile_breakdown.svg"
    assert manifest_path.name == "20260902_130405_vae_profile_breakdown.manifest.json"
    report = Path(result["report"])
    assert report.name == "20260902_130405_vae_profile_breakdown.md"
    assert svg_path.name in report.read_text()
    assert "| Total | 10 | 6 |" in report.read_text()
    svg = svg_path.read_text(encoding="utf-8")
    assert "VAE &lt;steady&gt; decode" in svg
    assert "Vectorize chunks" in svg
    assert "1.67x end-to-end" in svg
    assert "Unattributed" in svg

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["timestamp"] == "20260902_130405"
    assert manifest["normalized_input"]["profiles"][0]["total"] == 10.0
    assert manifest["input_sha256"]


def test_collision_suffix_preserves_timestamp(tmp_path):
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(_document()), encoding="utf-8")

    MODULE.render_file(input_path, tmp_path, prefix="vae", timestamp="20260902_130405")
    second = MODULE.render_file(
        input_path, tmp_path, prefix="vae", timestamp="20260902_130405"
    )

    assert Path(second["svg"]).name == "20260902_130405_vae_profile_breakdown_01.svg"


def test_report_collision_and_time_sorting_across_names(tmp_path):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(_document()))
    first = MODULE.render_file(
        source, tmp_path, prefix="z", timestamp="20260902_130405"
    )
    second = MODULE.render_file(
        source, tmp_path, prefix="a", timestamp="20260903_130405"
    )
    assert Path(first["report"]).name < Path(second["report"]).name
    Path(first["svg"]).unlink()
    Path(first["manifest"]).unlink()
    collision = MODULE.render_file(
        source, tmp_path, prefix="z", timestamp="20260902_130405"
    )
    assert Path(collision["report"]).name.endswith("_01.md")
    manifest = json.loads(Path(collision["manifest"]).read_text())
    assert manifest["output_report"] == collision["report"]


def test_rejects_component_sum_above_total():
    document = _document()
    document["profiles"][0]["total"] = 5.0

    with pytest.raises(MODULE.InputError, match="exceeds total"):
        MODULE.normalize_document(document)
