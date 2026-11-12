"""Unit tests for # CONCEPT: annotation extraction and CONCEPTS.md drift checking."""

from __future__ import annotations

from pathlib import Path

from scripts.collect_concepts import (
    collect_concepts,
    is_concepts_file_in_sync,
    render_concepts_markdown,
    run_cli,
)


def test_should_extract_concept_entries_and_verify_sync_with_check_flag(
    tmp_path: Path,
) -> None:
    src_dir = tmp_path / "src" / "pkg"
    src_dir.mkdir(parents=True)
    sample_py = src_dir / "sample.py"
    sample_py.write_text(
        "# CONCEPT: [System Design] Idempotent Consumer\n"
        "# Ensures duplicate messages produce the exact same state.\n"
        "def process() -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    grouped = collect_concepts(src_dir=tmp_path / "src", repo_root=tmp_path)
    rendered = render_concepts_markdown(grouped)

    assert "System Design" in grouped
    assert len(grouped["System Design"]) == 1
    entry = grouped["System Design"][0]
    assert entry.title == "Idempotent Consumer"
    assert entry.relative_path == "src/pkg/sample.py"
    assert entry.line_number == 1
    assert "duplicate messages" in entry.explanation
    assert "### Idempotent Consumer" in rendered
    assert is_concepts_file_in_sync(tmp_path / "CONCEPTS.md", rendered) is False

    assert run_cli(argv=["--check"], repo_root=tmp_path) == 1
    assert run_cli(argv=[], repo_root=tmp_path) == 0
    assert run_cli(argv=["--check"], repo_root=tmp_path) == 0
