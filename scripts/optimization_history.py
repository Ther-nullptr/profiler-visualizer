"""Validate measured optimization history and resolve explicit comparisons."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
import statistics
from typing import Any


class HistoryError(ValueError):
    """A ledger contains an ambiguous or unsupported performance claim."""


def text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoryError(f"{field} must be a non-empty string")
    return value.strip()


def number(value: Any, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoryError(f"{field} must be a number")
    value = float(value)
    if not math.isfinite(value) or (positive and value <= 0):
        raise HistoryError(
            f"{field} must be finite" + (" and positive" if positive else "")
        )
    return value


def choice(value: Any, allowed: tuple[str, ...], field: str) -> str:
    if value not in allowed:
        raise HistoryError(f"{field} must be one of {', '.join(allowed)}")
    return value


def timestamp(value: Any, field: str) -> str:
    value = text(value, field)
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("missing timezone")
    except ValueError as error:
        raise HistoryError(f"{field} must be ISO-8601 with timezone") from error
    return value


def strings(value: Any, field: str, *, required: bool = False) -> list[str]:
    if not isinstance(value, list) or (required and not value):
        raise HistoryError(f"{field} must be a {'non-empty ' if required else ''}list")
    result = [text(item, field) for item in value]
    if len(set(result)) != len(result):
        raise HistoryError(f"{field} has duplicate entries")
    return result


def object_value(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise HistoryError(f"{field} must be a non-empty object")
    try:
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError) as error:
        raise HistoryError(f"{field} must contain finite JSON values") from error
    return value


def has_unknown(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, dict):
        return any(has_unknown(item) for item in value.values())
    if isinstance(value, list):
        return any(has_unknown(item) for item in value)
    return False


def records(value: Any, field: str, *, required: bool = True) -> dict[str, dict]:
    if not isinstance(value, list) or (required and not value):
        raise HistoryError(f"{field} must be a {'non-empty ' if required else ''}list")
    result = {}
    for entry in value:
        if not isinstance(entry, dict):
            raise HistoryError(f"{field} entries must be objects")
        key = text(entry.get("id"), f"{field}.id")
        if key in result:
            raise HistoryError(f"duplicate {field} id: {key}")
        result[key] = entry
    return result


def metrics(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise HistoryError(f"{field} must be a list")
    result = []
    names = set()
    for item in value:
        if not isinstance(item, dict):
            raise HistoryError(f"{field} entries must be objects")
        name = text(item.get("name"), f"{field}.name")
        if name in names:
            raise HistoryError(f"duplicate metric: {name}")
        names.add(name)
        result.append(
            {
                "name": name,
                "value": number(item.get("value"), name),
                "unit": text(item.get("unit"), f"{name}.unit"),
            }
        )
    return result


def normalize_history(raw: Any) -> dict[str, Any]:
    if (
        not isinstance(raw, dict)
        or type(raw.get("schema_version")) is not int
        or raw["schema_version"] != 1
    ):
        raise HistoryError("history schema_version must be integer 1")
    title = text(raw.get("title"), "title")
    evidence_kind = choice(
        raw.get("evidence_kind"), ("measured", "synthetic"), "evidence_kind"
    )
    protocols = records(raw.get("protocols"), "protocols")
    states = records(raw.get("states"), "states")
    runs = records(raw.get("runs"), "runs")
    optimizations = records(
        raw.get("optimizations", []), "optimizations", required=False
    )
    comparisons = records(raw.get("comparisons", []), "comparisons", required=False)
    result = {
        "schema_version": 1,
        "title": title,
        "evidence_kind": evidence_kind,
        "current_run_id": text(raw.get("current_run_id"), "current_run_id"),
        "protocols": [],
        "states": [],
        "runs": [],
        "optimizations": [],
        "comparisons": [],
        "notes": strings(raw.get("notes", []), "notes"),
    }

    for key, source in protocols.items():
        metric = object_value(source.get("metric"), f"{key}.metric")
        original = source.get("original_state_id")
        if original is not None and original not in states:
            raise HistoryError(f"{key}: unknown original_state_id")
        result["protocols"].append(
            {
                "id": key,
                "label": text(source.get("label"), f"{key}.label"),
                "workload": object_value(source.get("workload"), f"{key}.workload"),
                "environment": object_value(
                    source.get("environment"), f"{key}.environment"
                ),
                "original_state_id": original,
                "metric": {
                    "name": text(metric.get("name"), f"{key}.metric.name"),
                    "unit": choice(
                        metric.get("unit"), ("s", "ms", "us"), f"{key}.metric.unit"
                    ),
                    "statistic": choice(
                        metric.get("statistic"),
                        ("mean", "median"),
                        f"{key}.metric.statistic",
                    ),
                },
            }
        )

    for key, source in optimizations.items():
        result["optimizations"].append(
            {
                "id": key,
                "label": text(source.get("label"), f"{key}.label"),
                "scope": choice(
                    source.get("scope"), ("shared", "precision"), f"{key}.scope"
                ),
            }
        )

    for key, source in states.items():
        parent = source.get("parent_id")
        if parent is not None and parent not in states:
            raise HistoryError(f"{key}: unknown parent_id")
        active = source.get("active_optimizations")
        if active is not None:
            active = strings(active, f"{key}.active_optimizations")
            if set(active) - optimizations.keys():
                raise HistoryError(f"{key}: unknown active optimization")
        shared = source.get("shared_config")
        if shared is not None:
            shared = object_value(shared, f"{key}.shared_config")
        result["states"].append(
            {
                "id": key,
                "label": text(source.get("label"), f"{key}.label"),
                "parent_id": parent,
                "revision": text(source.get("revision"), f"{key}.revision"),
                "precision": text(source.get("precision"), f"{key}.precision"),
                "classification": choice(
                    source.get("classification"),
                    ("reference", "exact", "numerical_exception", "lossy"),
                    f"{key}.classification",
                ),
                "status": choice(
                    source.get("status"),
                    ("accepted", "experimental", "rejected", "reverted"),
                    f"{key}.status",
                ),
                "description": text(source.get("description"), f"{key}.description"),
                "active_optimizations": active,
                "shared_config": shared,
            }
        )

    # Parent links describe recipes, not proof of a timing comparison.
    for key in states:
        visited = set()
        node = key
        while node is not None:
            if node in visited:
                raise HistoryError(f"state parent cycle at {node}")
            visited.add(node)
            node = states[node].get("parent_id")

    for key, source in runs.items():
        state_id = source.get("state_id")
        protocol_id = source.get("protocol_id")
        if state_id not in states or protocol_id not in protocols:
            raise HistoryError(f"{key}: unknown state_id or protocol_id")
        samples = source.get("samples")
        if not isinstance(samples, list) or not samples:
            raise HistoryError(
                f"{key}.samples must be a non-empty list of measured repetitions"
            )
        samples = [number(item, f"{key}.samples", positive=True) for item in samples]
        measured_at = source.get("measured_at")
        if measured_at is not None:
            measured_at = timestamp(measured_at, f"{key}.measured_at")
        recorded_at = timestamp(
            source.get("recorded_at", measured_at), f"{key}.recorded_at"
        )
        quality = source.get("quality", {"status": "unmeasured"})
        if not isinstance(quality, dict):
            raise HistoryError(f"{key}.quality must be an object")
        quality_status = choice(
            quality.get("status"),
            ("pass", "fail", "unmeasured"),
            f"{key}.quality.status",
        )
        quality_sources = strings(quality.get("sources", []), f"{key}.quality.sources")
        reference = quality.get("reference")
        assessment = quality.get("assessment")
        if quality_status != "unmeasured":
            reference = text(reference, f"{key}.quality.reference")
            assessment = text(assessment, f"{key}.quality.assessment")
            if not quality_sources:
                raise HistoryError(f"{key}: assessed quality requires sources")
        elif reference is not None:
            reference = text(reference, f"{key}.quality.reference")
        profile = source.get("profile")
        if profile is not None:
            if not isinstance(profile, dict):
                raise HistoryError(f"{key}.profile must be an object")
            profile = {
                "path": text(profile.get("path"), f"{key}.profile.path"),
                "name": text(profile.get("name"), f"{key}.profile.name"),
            }
        statistic = protocols[protocol_id]["metric"]["statistic"]
        result["runs"].append(
            {
                "id": key,
                "state_id": state_id,
                "protocol_id": protocol_id,
                "cohort_id": text(source.get("cohort_id"), f"{key}.cohort_id"),
                "measured_at": measured_at,
                "recorded_at": recorded_at,
                "samples": samples,
                "value": getattr(statistics, statistic)(samples),
                "min": min(samples),
                "max": max(samples),
                "std": statistics.stdev(samples) if len(samples) > 1 else None,
                "sources": strings(
                    source.get("sources"), f"{key}.sources", required=True
                ),
                "quality": {
                    "status": quality_status,
                    "reference": reference,
                    "assessment": assessment,
                    "sources": quality_sources,
                    "metrics": metrics(
                        quality.get("metrics", []), f"{key}.quality.metrics"
                    ),
                },
                "observations": metrics(
                    source.get("observations", []), f"{key}.observations"
                ),
                "profile": profile,
            }
        )

    state_index = {item["id"]: item for item in result["states"]}
    run_index = {item["id"]: item for item in result["runs"]}
    protocol_index = {item["id"]: item for item in result["protocols"]}
    seen = set()
    shared_optimizations = {
        key for key, opt in optimizations.items() if opt["scope"] == "shared"
    }
    for key, source in comparisons.items():
        kind = choice(
            source.get("kind"),
            ("incremental", "cumulative", "matched_precision"),
            f"{key}.kind",
        )
        before = source.get("baseline_run_id")
        after = source.get("candidate_run_id")
        if before not in run_index or after not in run_index or before == after:
            raise HistoryError(f"{key}: invalid comparison run IDs")
        pair = (after, kind)
        if pair in seen:
            raise HistoryError(f"{after}: duplicate comparison kind {kind}")
        seen.add(pair)
        baseline, candidate = run_index[before], run_index[after]
        if (
            baseline["protocol_id"] != candidate["protocol_id"]
            or baseline["cohort_id"] != candidate["cohort_id"]
        ):
            raise HistoryError(
                f"{key}: comparison crosses protocol or measurement cohort"
            )
        bstate, cstate = (
            state_index[baseline["state_id"]],
            state_index[candidate["state_id"]],
        )
        if kind == "incremental" and cstate["parent_id"] != bstate["id"]:
            raise HistoryError(
                f"{key}: incremental comparison must use the parent state"
            )
        if kind == "cumulative":
            original = protocol_index[candidate["protocol_id"]]["original_state_id"]
            if original is None or bstate["id"] != original:
                raise HistoryError(
                    f"{key}: cumulative comparison must use the explicit original anchor"
                )
        if kind == "matched_precision":
            if bstate["precision"].lower() not in ("bf16", "fp16", "w16a16"):
                raise HistoryError(
                    f"{key}: matched precision baseline must be BF16/FP16/W16A16"
                )
            if bstate["precision"].lower() == cstate["precision"].lower():
                raise HistoryError(
                    f"{key}: matched precision needs distinct precision tiers"
                )
            if (
                has_unknown(bstate["shared_config"])
                or bstate["shared_config"] != cstate["shared_config"]
            ):
                raise HistoryError(
                    f"{key}: matched precision requires identical known shared_config"
                )
            if (
                bstate["active_optimizations"] is None
                or cstate["active_optimizations"] is None
            ):
                raise HistoryError(
                    f"{key}: matched precision requires known optimization coverage"
                )
            if (
                set(bstate["active_optimizations"]) & shared_optimizations
                != set(cstate["active_optimizations"]) & shared_optimizations
            ):
                raise HistoryError(
                    f"{key}: matched precision has unequal shared optimization coverage"
                )
        result["comparisons"].append(
            {
                "id": key,
                "kind": kind,
                "label": text(source.get("label"), f"{key}.label"),
                "baseline_run_id": before,
                "candidate_run_id": after,
                "speedup": baseline["value"] / candidate["value"],
                "saved": baseline["value"] - candidate["value"],
                "saved_percent": (baseline["value"] - candidate["value"])
                / baseline["value"]
                * 100,
            }
        )
    if result["current_run_id"] not in run_index:
        raise HistoryError("unknown current_run_id")
    return result


def load_history(path: Path, *, content: bytes | None = None) -> dict[str, Any]:
    try:
        return normalize_history(
            json.loads(path.read_bytes() if content is None else content)
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HistoryError(f"cannot parse ledger: {error}") from error
