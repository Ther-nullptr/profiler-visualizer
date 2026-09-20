import copy
import json
from pathlib import Path
import re
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from optimization_history import HistoryError, normalize_history
import render_optimization_history as renderer


def ledger():
    states = []
    runs = []
    for index, (name, parent, precision, value) in enumerate(
        (
            ("original", None, "bf16", 100),
            ("common", "original", "bf16", 80),
            ("fp8", "common", "fp8", 65),
            ("fp4", "common", "w4a4", 50),
        )
    ):
        states.append(
            {
                "id": name,
                "label": name.upper(),
                "parent_id": parent,
                "revision": f"fixture-{index}",
                "precision": precision,
                "classification": (
                    "reference"
                    if not parent
                    else "exact" if name == "common" else "lossy"
                ),
                "status": "rejected" if name == "fp4" else "accepted",
                "description": f"Synthetic {name} state",
                "shared_config": {"decoder": "wan", "attention": "fixed"},
                "active_optimizations": [] if not parent else ["fusion"],
            }
        )
        runs.append(
            {
                "id": name,
                "state_id": name,
                "protocol_id": "fixed",
                "cohort_id": "paired-session",
                "measured_at": f"2026-09-15T10:0{index}:00+08:00",
                "samples": [value - 1, value + 1],
                "sources": ["Synthetic test fixture, not measured performance"],
                "quality": {"status": "unmeasured"},
            }
        )
    runs[-1]["quality"] = {
        "status": "fail",
        "reference": "synthetic original",
        "assessment": "Synthetic rejection case",
        "sources": ["synthetic quality fixture"],
        "metrics": [{"name": "Reference consistency", "value": 0.7, "unit": "score"}],
    }
    comparisons = []
    for name in ("common", "fp8", "fp4"):
        comparisons.extend(
            [
                {
                    "id": f"{name}-step",
                    "label": f"Apply {name}",
                    "kind": "incremental",
                    "baseline_run_id": "original" if name == "common" else "common",
                    "candidate_run_id": name,
                },
                {
                    "id": f"{name}-total",
                    "label": f"Original versus {name}",
                    "kind": "cumulative",
                    "baseline_run_id": "original",
                    "candidate_run_id": name,
                },
            ]
        )
    comparisons.append(
        {
            "id": "fp8-fair",
            "label": "Matched BF16 versus FP8",
            "kind": "matched_precision",
            "baseline_run_id": "common",
            "candidate_run_id": "fp8",
        }
    )
    return {
        "schema_version": 1,
        "title": "Synthetic optimization history",
        "evidence_kind": "synthetic",
        "current_run_id": "fp8",
        "protocols": [
            {
                "id": "fixed",
                "label": "Fixed fixture",
                "original_state_id": "original",
                "workload": {
                    "model": "fixture",
                    "shape": "fixed",
                    "warmup": "excluded",
                },
                "environment": {"hardware": "fixture", "clocks": "fixed"},
                "metric": {
                    "name": "Complete service",
                    "unit": "ms",
                    "statistic": "mean",
                },
            }
        ],
        "optimizations": [
            {"id": "fusion", "label": "Common fusion", "scope": "shared"}
        ],
        "states": states,
        "runs": runs,
        "comparisons": comparisons,
    }


def write_ledger(tmp_path, document=None):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(document or ledger()), encoding="utf-8")
    return path


def test_direct_ratios_and_explicit_designated_current():
    result = normalize_history(ledger())
    edges = {item["id"]: item for item in result["comparisons"]}
    assert edges["fp8-total"]["speedup"] == pytest.approx(100 / 65)
    assert edges["fp8-fair"]["speedup"] == pytest.approx(80 / 65)
    assert edges["fp8-step"]["saved"] == pytest.approx(15)
    assert result["current_run_id"] == "fp8"
    assert result["states"][-1]["status"] == "rejected"
    assert result["runs"][-1]["quality"]["status"] == "fail"


def test_missing_cumulative_edge_is_not_inferred_from_parent_chain(tmp_path):
    source = ledger()
    source["comparisons"] = [
        c for c in source["comparisons"] if c["kind"] == "incremental"
    ]
    result = normalize_history(source)
    assert all(c["kind"] == "incremental" for c in result["comparisons"])
    rendered = renderer.render_file(write_ledger(tmp_path, source), tmp_path)
    assert "Pending comparison" in Path(rendered["html"]).read_text()


@pytest.mark.parametrize("field", ["protocol_id", "cohort_id"])
def test_rejects_cross_protocol_or_cohort_comparisons(field):
    source = ledger()
    source["protocols"].append(dict(source["protocols"][0], id="other"))
    source["runs"][2][field] = "other"
    with pytest.raises(HistoryError, match="crosses protocol or measurement cohort"):
        normalize_history(source)


@pytest.mark.parametrize(
    "change", ["decoder", "unknown", "coverage", "unknown_coverage"]
)
def test_matched_precision_requires_same_known_shared_configuration(change):
    source = ledger()
    state = source["states"][2]
    if change == "decoder":
        state["shared_config"]["decoder"] = "taehv"
    elif change == "unknown":
        state["shared_config"] = None
    elif change == "coverage":
        state["active_optimizations"] = []
    else:
        state["active_optimizations"] = None
    with pytest.raises(HistoryError, match="matched precision"):
        normalize_history(source)


def test_precision_specific_optimization_does_not_invalidate_shared_parity():
    source = ledger()
    source["optimizations"].append(
        {"id": "fp8-pack", "label": "FP8 pack", "scope": "precision"}
    )
    source["states"][2]["active_optimizations"].append("fp8-pack")
    normalize_history(source)


@pytest.mark.parametrize("value", [None, {"mode": None}, [{"mode": None}]])
def test_nested_unknown_settings_do_not_establish_precision_parity(value):
    source = ledger()
    for state in source["states"][1:3]:
        state["shared_config"]["decoder"] = copy.deepcopy(value)
    with pytest.raises(HistoryError, match="identical known shared_config"):
        normalize_history(source)


def test_explicit_disabled_setting_is_known():
    source = ledger()
    for state in source["states"][1:3]:
        state["shared_config"]["graph"] = False
    normalize_history(source)


def test_unknown_coverage_is_not_known_empty():
    source = ledger()
    source["comparisons"] = []
    source["states"][2].pop("active_optimizations")
    assert normalize_history(source)["states"][2]["active_optimizations"] is None


@pytest.mark.parametrize(
    "samples", [[], [0], [-1], [True], [float("inf")], [float("nan")]]
)
def test_rejects_invalid_or_missing_samples(samples):
    source = ledger()
    source["runs"][0]["samples"] = samples
    with pytest.raises(HistoryError, match="samples"):
        normalize_history(source)


def test_median_is_computed_from_samples_not_supplied_summary():
    source = ledger()
    source["protocols"][0]["metric"]["statistic"] = "median"
    source["runs"][0]["samples"] = [10, 20, 300]
    source["runs"][0]["value"] = 9999
    run = normalize_history(source)["runs"][0]
    assert run["value"] == 20
    assert run["min"] == 10
    assert run["max"] == 300


@pytest.mark.parametrize(
    "mutate, error",
    [
        (lambda d: d["states"][0].update(parent_id="fp8"), "cycle"),
        (lambda d: d["states"][0].update(parent_id="missing"), "unknown parent"),
        (lambda d: d["protocols"][0].update(original_state_id=None), "original anchor"),
        (
            lambda d: d["comparisons"][2].update(baseline_run_id="original"),
            "parent state",
        ),
        (lambda d: d["runs"][0].update(measured_at="2026-09-15T10:00:00"), "timezone"),
        (lambda d: d["runs"][0].update(sources=[]), "sources"),
        (lambda d: d["runs"].append(copy.deepcopy(d["runs"][0])), "duplicate runs"),
        (
            lambda d: d["states"][1].update(active_optimizations=["unknown"]),
            "unknown active",
        ),
        (lambda d: d.update(current_run_id="missing"), "current_run_id"),
        (
            lambda d: d["protocols"][0]["environment"].update(clock=float("nan")),
            "finite JSON",
        ),
    ],
)
def test_rejects_inconsistent_history(mutate, error):
    source = ledger()
    mutate(source)
    with pytest.raises(HistoryError, match=error):
        normalize_history(source)


def test_quality_pass_requires_assessment_reference_and_sources():
    source = ledger()
    source["runs"][0]["quality"] = {"status": "pass"}
    with pytest.raises(HistoryError, match="quality.reference"):
        normalize_history(source)


def test_import_can_preserve_unknown_measurement_time(tmp_path):
    source = ledger()
    run = source["runs"][0]
    run["recorded_at"] = run.pop("measured_at")
    normalized = normalize_history(source)["runs"][0]
    assert normalized["measured_at"] is None
    assert normalized["recorded_at"] == "2026-09-15T10:00:00+08:00"
    renderer.render_file(write_ledger(tmp_path, source), tmp_path)


def test_negative_savings_are_retained_as_a_regression(tmp_path):
    source = ledger()
    source["runs"][2]["samples"] = [89, 91]
    path = write_ledger(tmp_path, source)
    result = renderer.render_file(path, tmp_path)
    page = Path(result["html"]).read_text()
    assert 'class="regression"' in page
    assert "-10.000 ms" in page


def test_render_is_offline_timestamped_and_collision_safe(tmp_path):
    path = write_ledger(tmp_path)
    first = renderer.render_file(
        path, tmp_path, prefix="case", timestamp="20260915_140000", update_index=True
    )
    page = Path(first["html"]).read_text()
    assert Path(first["html"]).name == "20260915_140000_case_optimization_history.html"
    assert Path(first["report"]).name == "20260915_140000_case_optimization_history.md"
    assert "SYNTHETIC FIXTURE / NOT PERFORMANCE EVIDENCE" in page
    assert "<script src=" not in page
    assert Path(first["index"]).read_text() == page
    manifest = json.loads(Path(first["manifest"]).read_text())
    assert manifest["input_sha256"]
    assert manifest["normalized_input"]["current_run_id"] == "fp8"
    assert manifest["normalized_input"]["runs"][0]["samples"] == [99, 101]
    second = renderer.render_file(
        path, tmp_path, prefix="case", timestamp="20260915_140000"
    )
    assert Path(second["html"]).name.endswith("_01.html")
    Path(first["html"]).unlink()
    third = renderer.render_file(
        path, tmp_path, prefix="case", timestamp="20260915_140000"
    )
    assert Path(third["html"]).name.endswith("_02.html")


def test_unsafe_metadata_and_source_urls_are_not_executable(tmp_path):
    source = ledger()
    source["title"] = "<script>alert('title')</script>"
    source["states"][0]["label"] = '<img src=x onerror="alert(1)">'
    source["runs"][0]["sources"] = ["javascript:alert(1)"]
    result = renderer.render_file(write_ledger(tmp_path, source), tmp_path)
    page = Path(result["html"]).read_text()
    assert "&lt;script&gt;" in page
    assert "<img src=x" not in page
    assert '<a href="javascript:' not in page


def test_existing_breakdown_is_reused_with_its_own_boundary(tmp_path):
    source = ledger()
    profile = {
        "schema_version": 1,
        "title": "GPU fixture",
        "metric": {
            "name": "GPU operation time",
            "unit": "ms",
            "aggregation": "one profiled chunk",
        },
        "profiles": [
            {"name": "FP8", "total": 9, "components": [{"name": "GEMM", "value": 9}]}
        ],
    }
    (tmp_path / "profile.json").write_text(json.dumps(profile))
    source["runs"][2]["profile"] = {"path": "profile.json", "name": "FP8"}
    result = renderer.render_file(write_ledger(tmp_path, source), tmp_path)
    page = Path(result["html"]).read_text()
    assert "data:image/svg+xml;base64," in page
    assert "GPU operation time / one profiled chunk" in page
    assert "65.000 ms" in page
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["profile_sources"][0]["sha256"]
    source["runs"][2]["profile"]["name"] = "wrong"
    with pytest.raises(HistoryError, match="unknown profile name"):
        renderer.render_file(write_ledger(tmp_path, source), tmp_path)


def test_missing_profile_is_visible_without_fabricating_components(tmp_path):
    source = ledger()
    source["runs"][2]["profile"] = {"path": "missing.json", "name": "FP8"}
    result = renderer.render_file(write_ledger(tmp_path, source), tmp_path)
    page = Path(result["html"]).read_text()
    assert "profile unavailable" in page
    assert "data:image/svg+xml;base64," not in page


def test_validate_only_does_not_write_outputs(tmp_path, capsys):
    path = write_ledger(tmp_path)
    assert renderer.main([str(path), "--validate-only"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"]
    assert list(tmp_path.iterdir()) == [path]


def test_documented_fixture_validates():
    guide = (SCRIPTS.parent / "references/optimization-history.md").read_text()
    examples = [
        json.loads(block)
        for block in re.findall(r"```json\n(.*?)\n```", guide, re.DOTALL)
    ]
    source = next(example for example in examples if "schema_version" in example)
    assert normalize_history(source)["comparisons"][0]["speedup"] == 1.25


def test_timing_and_quality_source_changes_are_fingerprinted(tmp_path):
    source = ledger()
    timing = tmp_path / "timing.txt"
    quality = tmp_path / "quality.txt"
    timing.write_text("first timing evidence")
    quality.write_text("first quality evidence")
    source["runs"][0]["sources"] = ["timing.txt"]
    source["runs"][0]["quality"]["sources"] = ["quality.txt"]
    path = write_ledger(tmp_path, source)
    first = renderer.render_file(path, tmp_path)
    before = json.loads(Path(first["manifest"]).read_text())
    timing.write_text("changed timing evidence")
    quality.write_text("changed quality evidence")
    second = renderer.render_file(path, tmp_path)
    after = json.loads(Path(second["manifest"]).read_text())
    assert before["input_sha256"] == after["input_sha256"]
    for name in ("timing.txt", "quality.txt"):
        old = next(item for item in before["source_evidence"] if item["source"] == name)
        new = next(item for item in after["source_evidence"] if item["source"] == name)
        assert old["status"] == new["status"] == "hashed"
        assert old["sha256"] != new["sha256"]


def test_large_missing_and_external_sources_remain_explicit(tmp_path, monkeypatch):
    source = ledger()
    source["runs"][0]["sources"] = [
        "large.bin",
        "missing.json",
        "https://example.invalid/evidence",
    ]
    (tmp_path / "large.bin").write_bytes(b"123456789")
    monkeypatch.setattr(renderer, "MAX_SOURCE_HASH_BYTES", 8)
    result = renderer.fingerprint_sources(normalize_history(source), tmp_path)
    indexed = {item["source"]: item for item in result}
    assert indexed["large.bin"]["status"] == "not_hashed_large"
    assert "sha256" not in indexed["large.bin"]
    assert indexed["missing.json"]["status"] == "unavailable"
    assert (
        indexed["https://example.invalid/evidence"]["status"] == "external_not_fetched"
    )


def test_html_preserves_baseline_identity_even_for_equal_means(tmp_path):
    source = ledger()
    source["runs"].append(dict(source["runs"][0], id="original-repeat"))
    first = renderer.render_html(
        normalize_history(source), {}, "fixed", tmp_path, tmp_path
    )
    edge = next(item for item in source["comparisons"] if item["id"] == "fp8-total")
    edge["baseline_run_id"] = "original-repeat"
    second = renderer.render_html(
        normalize_history(source), {}, "fixed", tmp_path, tmp_path
    )
    assert first != second
    assert "baseline: original-repeat" in second
    assert "original-repeat &rarr; fp8" in second


@pytest.mark.parametrize("case", ["malformed", "unknown_name"])
def test_validate_only_checks_referenced_profiles(tmp_path, capsys, case):
    source = ledger()
    source["runs"][0]["profile"] = {"path": "profile.json", "name": "missing"}
    profile = (
        {}
        if case == "malformed"
        else {
            "schema_version": 1,
            "title": "fixture",
            "metric": {"name": "GPU", "unit": "ms", "aggregation": "sum"},
            "profiles": [
                {"name": "actual", "components": [{"name": "kernel", "value": 1}]}
            ],
        }
    )
    (tmp_path / "profile.json").write_text(json.dumps(profile))
    path = write_ledger(tmp_path, source)
    assert renderer.main([str(path), "--validate-only"]) == 2
    error = capsys.readouterr().err
    assert (
        "invalid profile" in error
        if case == "malformed"
        else "unknown profile name" in error
    )
    assert not list(tmp_path.glob("*.html"))


def test_validate_only_reports_missing_profile_warning(tmp_path, capsys):
    source = ledger()
    source["runs"][0]["profile"] = {"path": "missing.json", "name": "missing"}
    assert renderer.main([str(write_ledger(tmp_path, source)), "--validate-only"]) == 0
    assert "profile unavailable" in json.loads(capsys.readouterr().out)["warnings"][0]
