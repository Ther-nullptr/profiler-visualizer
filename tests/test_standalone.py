import ast
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = (
    "README.md",
    "README.zh-CN.md",
    "CONTRIBUTING.md",
    "PROVENANCE.md",
    "SKILL.md",
    "references/input-schema.md",
    "references/optimization-history.md",
)


@pytest.mark.parametrize("name", DOCS)
def test_documentation_links_stay_inside_standalone_checkout(name):
    source = ROOT / name
    for link in re.findall(r"!?\[[^\]]+\]\(([^)]+)\)", source.read_text()):
        if link.startswith(("http://", "https://", "#")):
            continue
        path = (source.parent / link.split("#", 1)[0]).resolve()
        assert path.is_relative_to(ROOT), (name, link)
        assert path.is_file(), (name, link)


def test_bilingual_readme_commands_match():
    blocks = [
        re.findall(r"```bash\n(.*?)\n```", (ROOT / name).read_text(), re.DOTALL)
        for name in ("README.md", "README.zh-CN.md")
    ]
    assert blocks[0]
    assert blocks[0] == blocks[1]


def test_skill_name_and_metadata_remain_compatible():
    frontmatter = (ROOT / "SKILL.md").read_text().split("---", 2)[1]
    assert yaml.safe_load(frontmatter)["name"] == "profile-visualizer"
    metadata = yaml.safe_load((ROOT / "agents/openai.yaml").read_text())
    assert "$profile-visualizer" in metadata["interface"]["default_prompt"]


def test_scripts_parse_as_python_310():
    for path in (ROOT / "scripts").glob("*.py"):
        ast.parse(path.read_text(), filename=str(path), feature_version=(3, 10))


def test_examples_are_self_contained_and_png_runs_in_isolation(tmp_path):
    pytest.importorskip("cairosvg")
    isolated = tmp_path / "standalone"
    for name in ("scripts", "assets", "examples"):
        shutil.copytree(ROOT / name, isolated / name)
    history = json.loads((isolated / "examples/history.json").read_text())
    assert history["evidence_kind"] == "synthetic"
    assert all(
        not Path(ref["profile"]["path"]).is_absolute()
        for ref in history["runs"]
        if ref.get("profile")
    )
    process = subprocess.run(
        [
            sys.executable,
            "-I",
            str(isolated / "scripts/render_optimization_history.py"),
            str(isolated / "examples/history.json"),
            "--output-dir",
            str(isolated / "outputs"),
            "--png-scale",
            "0.4",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(process.stdout)
    assert "html" not in result
    assert Path(result["png"]).is_file()
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert len(manifest["profile_sources"]) == 1
    assert manifest["normalized_input"]["current_run_id"] == "fp8-run"
    assert all(item["status"] == "hashed" for item in manifest["source_evidence"])


def test_example_svg_breakdown_runs_without_sibling_skills(tmp_path):
    process = subprocess.run(
        [
            sys.executable,
            "-I",
            str(ROOT / "scripts/render_profile_breakdown.py"),
            str(ROOT / "examples/profile.json"),
            "--output-dir",
            str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(process.stdout)
    assert Path(result["svg"]).is_file()
    assert "SYNTHETIC" in Path(result["svg"]).read_text()
