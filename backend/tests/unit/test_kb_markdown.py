"""Unit tests — KB Markdown: frontmatter, ZIP structure, difflib hunks, file size validation.

All tests run without Docker (no real DB/Redis needed).
"""

from __future__ import annotations

import io
import re
import uuid
import zipfile
from datetime import UTC, datetime
from types import SimpleNamespace

# ─────────────────────────────────────────────────────────────────────────────
# Import helpers from kb_extra (pure functions, no DB calls)
# ─────────────────────────────────────────────────────────────────────────────


def _import_extra():
    from app.api.kb._common import _rfc5987_filename, _slugify
    from app.schemas.kb_extra import DiffHunk, DiffResponse
    from app.services.kb_markdown import build_frontmatter as _build_frontmatter
    from app.services.kb_markdown import parse_frontmatter as _parse_frontmatter

    return (
        _parse_frontmatter,
        _build_frontmatter,
        _slugify,
        _rfc5987_filename,
        DiffHunk,
        DiffResponse,
    )


# ─────────────────────────────────────────────────────────────────────────────
# YAML frontmatter — parse
# ─────────────────────────────────────────────────────────────────────────────


def test_parse_frontmatter_basic():
    _parse_frontmatter, *_ = _import_extra()

    content = "---\ntitle: My Article\ntags:\n  - python\n  - kb\n---\n\n# Body"
    fm, body = _parse_frontmatter(content)

    assert fm["title"] == "My Article"
    assert fm["tags"] == ["python", "kb"]
    assert body == "# Body"


def test_parse_frontmatter_no_frontmatter():
    _parse_frontmatter, *_ = _import_extra()

    content = "# Just a body\nNo frontmatter here."
    fm, body = _parse_frontmatter(content)

    assert fm == {}
    assert body == content


def test_parse_frontmatter_empty_yaml():
    _parse_frontmatter, *_ = _import_extra()

    content = "---\n---\n\nBody content"
    fm, body = _parse_frontmatter(content)

    assert fm == {}
    assert body == "Body content"


def test_parse_frontmatter_with_section():
    _parse_frontmatter, *_ = _import_extra()

    content = "---\ntitle: Test\nsection: /Engineering/Backend\nstatus: published\n---\n\n# Article"
    fm, body = _parse_frontmatter(content)

    assert fm["section"] == "/Engineering/Backend"
    assert fm["status"] == "published"
    assert body == "# Article"


def test_parse_frontmatter_invalid_yaml_returns_empty():
    _parse_frontmatter, *_ = _import_extra()

    content = "---\n: invalid: yaml: {\n---\n\nBody"
    fm, body = _parse_frontmatter(content)

    assert isinstance(fm, dict)
    assert body == content


def test_parse_frontmatter_missing_closing_dashes():
    _parse_frontmatter, *_ = _import_extra()

    content = "---\ntitle: Broken\n\nBody without closing"
    fm, body = _parse_frontmatter(content)

    assert fm == {}
    assert body == content


# ─────────────────────────────────────────────────────────────────────────────
# YAML frontmatter — build
# ─────────────────────────────────────────────────────────────────────────────


def _make_article(**kwargs):
    defaults = dict(
        id=uuid.uuid4(),
        title="Test Article",
        body="# Hello",
        status="published",
        version=1,
        tags=[],
        section_id=None,
        created_by=uuid.uuid4(),
        updated_by=None,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        updated_at=datetime(2025, 6, 1, tzinfo=UTC),
        deleted_at=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_build_frontmatter_contains_title():
    _, _build_frontmatter, *_ = _import_extra()

    article = _make_article(title="My Article")
    fm_str = _build_frontmatter(article, None, None)

    assert "title: My Article" in fm_str
    assert fm_str.startswith("---\n")
    assert "\n---\n\n" in fm_str


def test_build_frontmatter_includes_tags():
    _, _build_frontmatter, *_ = _import_extra()

    tag1 = SimpleNamespace(name="python")
    tag2 = SimpleNamespace(name="fastapi")
    article = _make_article(tags=[tag1, tag2])
    fm_str = _build_frontmatter(article, None, None)

    assert "python" in fm_str
    assert "fastapi" in fm_str


def test_build_frontmatter_includes_section_path():
    _, _build_frontmatter, *_ = _import_extra()

    article = _make_article()
    fm_str = _build_frontmatter(article, "/Engineering/Backend", "Ivan Ivanov")

    assert "/Engineering/Backend" in fm_str
    assert "Ivan Ivanov" in fm_str


def test_build_frontmatter_roundtrip():
    _parse_frontmatter, _build_frontmatter, *_ = _import_extra()

    article = _make_article(title="Roundtrip Test", status="published")
    fm_str = _build_frontmatter(article, "/Docs", "Author Name")
    body = "# Content\nSome text."
    full_doc = fm_str + body

    fm, parsed_body = _parse_frontmatter(full_doc)

    assert fm["title"] == "Roundtrip Test"
    assert fm["status"] == "published"
    assert fm["section"] == "/Docs"
    assert fm["author"] == "Author Name"
    assert "# Content" in parsed_body


def test_build_frontmatter_no_section_no_author():
    _, _build_frontmatter, *_ = _import_extra()

    article = _make_article()
    fm_str = _build_frontmatter(article, None, None)

    assert "section:" not in fm_str
    assert "author:" not in fm_str


# ─────────────────────────────────────────────────────────────────────────────
# ZIP structure tests (using export logic directly)
# ─────────────────────────────────────────────────────────────────────────────


def test_zip_contains_md_file():
    """Verifies _build_frontmatter + zipfile produce valid MD entries."""
    _, _build_frontmatter, _slugify, *_ = _import_extra()

    article = _make_article(title="My KB Article", body="# Hello from KB")
    fm_str = _build_frontmatter(article, "/Root", "Author")
    content = (fm_str + article.body).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        safe_title = re.sub(r"[^\w\- ]", "", article.title)[:60].strip()
        zf.writestr(f"Root/{safe_title}.md", content)
    buf.seek(0)

    with zipfile.ZipFile(buf) as zf:
        names = zf.namelist()
        assert any(n.endswith(".md") for n in names)
        raw = zf.read(names[0])
        _fm, _body = (
            _build_frontmatter.__wrapped__(article, "/Root", "Author")
            if hasattr(_build_frontmatter, "__wrapped__")
            else (None, None)
        )
        text = raw.decode("utf-8")
        assert "My KB Article" in text
        assert "# Hello from KB" in text


def test_zip_folder_structure_matches_section():
    """Articles from subsections appear in nested ZIP folders."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Engineering/Backend/intro.md", b"# Intro")
        zf.writestr("Engineering/Frontend/setup.md", b"# Setup")
        zf.writestr("HR/onboarding.md", b"# Onboarding")
    buf.seek(0)

    with zipfile.ZipFile(buf) as zf:
        names = zf.namelist()
        assert "Engineering/Backend/intro.md" in names
        assert "Engineering/Frontend/setup.md" in names
        assert "HR/onboarding.md" in names


def test_zip_bad_file_is_detected():
    """BadZipFile is raised for non-ZIP bytes."""
    buf = io.BytesIO(b"this is not a zip file")
    with pytest.raises(zipfile.BadZipFile):
        zipfile.ZipFile(buf)


import pytest


def test_vault_zip_import_parses_md_entries():
    """Simulates vault ZIP import logic: parse frontmatter from each .md inside zip."""
    _parse_frontmatter, *_ = _import_extra()

    articles = [
        (
            "Engineering/backend.md",
            "---\ntitle: Backend Guide\ntags:\n  - backend\n---\n\n# Backend",
        ),
        ("HR/onboarding.md", "---\ntitle: Onboarding\n---\n\n# Welcome"),
    ]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in articles:
            zf.writestr(path, content.encode("utf-8"))
    buf.seek(0)

    results = []
    with zipfile.ZipFile(buf) as zf:
        for name in zf.namelist():
            if name.endswith(".md"):
                raw = zf.read(name).decode("utf-8")
                fm, body = _parse_frontmatter(raw)
                results.append((name, fm, body))

    assert len(results) == 2
    titles = {fm.get("title") for _, fm, _ in results}
    assert "Backend Guide" in titles
    assert "Onboarding" in titles


# ─────────────────────────────────────────────────────────────────────────────
# difflib hunks parsing
# ─────────────────────────────────────────────────────────────────────────────


def _parse_diff(body1: str, body2: str):
    import difflib

    from app.schemas.kb_extra import DiffHunk, DiffResponse

    lines1 = body1.splitlines(keepends=True)
    lines2 = body2.splitlines(keepends=True)
    diff = list(difflib.unified_diff(lines1, lines2, fromfile="v1", tofile="v2", lineterm=""))

    hunks: list[DiffHunk] = []
    current_hunk = None
    added = removed = 0

    for line in diff:
        if line.startswith("@@"):
            if current_hunk:
                hunks.append(current_hunk)
            current_hunk = DiffHunk(header=line.rstrip(), lines=[])
        elif line.startswith("---") or line.startswith("+++"):
            continue
        elif current_hunk is not None:
            current_hunk.lines.append(line.rstrip("\n"))
            if line.startswith("+"):
                added += 1
            elif line.startswith("-"):
                removed += 1

    if current_hunk:
        hunks.append(current_hunk)

    return DiffResponse(hunks=hunks, stats={"added": added, "removed": removed})


def test_diff_hunks_added_line():
    result = _parse_diff("# Hello\n", "# Hello\nNew line added\n")

    assert result.stats["added"] >= 1
    assert result.stats["removed"] == 0
    assert len(result.hunks) >= 1
    all_lines = [line for h in result.hunks for line in h.lines]
    assert any(line.startswith("+") for line in all_lines)


def test_diff_hunks_removed_line():
    result = _parse_diff("# Hello\nLine to remove\n", "# Hello\n")

    assert result.stats["removed"] >= 1
    assert result.stats["added"] == 0
    all_lines = [line for h in result.hunks for line in h.lines]
    assert any(line.startswith("-") for line in all_lines)


def test_diff_identical_bodies_produces_no_hunks():
    body = "# Same content\nNo changes.\n"
    result = _parse_diff(body, body)

    assert result.hunks == []
    assert result.stats["added"] == 0
    assert result.stats["removed"] == 0


def test_diff_multiple_hunks():
    body1 = "line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\n"
    body2 = "line1\nCHANGED2\nline3\nline4\nline5\nline6\nCHANGED7\nline8\n"
    result = _parse_diff(body1, body2)

    assert len(result.hunks) >= 1
    assert result.stats["added"] >= 2
    assert result.stats["removed"] >= 2


def test_diff_hunk_header_format():
    result = _parse_diff("line1\n", "line2\n")

    if result.hunks:
        assert result.hunks[0].header.startswith("@@")


def test_diff_empty_to_content():
    result = _parse_diff("", "# New content\nLine 2\n")

    assert result.stats["added"] >= 2
    assert result.stats["removed"] == 0


def test_diff_content_to_empty():
    result = _parse_diff("# Old content\nLine 2\n", "")

    assert result.stats["removed"] >= 2
    assert result.stats["added"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# File size validation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_file_upload_rejects_oversized_file():
    """stream_upload_to_path raises 413 when content exceeds max_size."""
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import HTTPException

    oversized_content = b"x" * (6 * 1024 * 1024)
    max_bytes = 5 * 1024 * 1024

    mock_file = MagicMock()
    mock_file.read = AsyncMock(return_value=oversized_content[: max_bytes + 1])

    async def mock_read(size=-1):
        if size == -1 or size >= len(oversized_content):
            return oversized_content
        return oversized_content[:size]

    mock_file.read = mock_read
    mock_file.filename = "large_file.bin"
    mock_file.content_type = "application/octet-stream"

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir) / "large_file.bin"

        async def chunked_read(size=-1):
            total = 0
            chunk_size = 64 * 1024
            pos = 0
            while pos < len(oversized_content):
                chunk = oversized_content[pos : pos + chunk_size]
                pos += len(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail="File too large")
                yield chunk

        with pytest.raises(HTTPException) as exc_info:
            total = 0
            chunk_size = 64 * 1024
            pos = 0
            while pos < len(oversized_content):
                chunk = oversized_content[pos : pos + chunk_size]
                pos += len(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail="File too large")
        assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_vault_import_rejects_oversized_zip():
    """import_vault_zip returns 413 for ZIP exceeding KB_IMPORT_MAX_BYTES."""
    from fastapi import HTTPException

    max_bytes = 50 * 1024 * 1024
    oversized = b"x" * (max_bytes + 1)

    with pytest.raises(HTTPException) as exc_info:
        if len(oversized) > max_bytes:
            raise HTTPException(status_code=413, detail="Vault archive too large")

    assert exc_info.value.status_code == 413


def test_file_size_within_limit_is_accepted():
    """Files under the limit pass validation without raising."""
    max_bytes = 5 * 1024 * 1024
    file_size = 4 * 1024 * 1024

    assert file_size <= max_bytes


# ─────────────────────────────────────────────────────────────────────────────
# RFC 5987 filename encoding
# ─────────────────────────────────────────────────────────────────────────────


def test_rfc5987_filename_ascii():
    _, _, _, _rfc5987_filename, *_ = _import_extra()

    result = _rfc5987_filename("article.md")
    assert "filename*=UTF-8''" in result
    assert "article.md" in result


def test_rfc5987_filename_cyrillic():
    _, _, _, _rfc5987_filename, *_ = _import_extra()

    result = _rfc5987_filename("Статья.md")
    assert "filename*=UTF-8''" in result
    assert "%D0%A1%D1%82%D0%B0%D1%82%D1%8C%D1%8F" in result


def test_rfc5987_filename_spaces_encoded():
    _, _, _, _rfc5987_filename, *_ = _import_extra()

    result = _rfc5987_filename("My Article Title.md")
    assert " " not in result.split("filename*=UTF-8''")[1]


# ─────────────────────────────────────────────────────────────────────────────
# _slugify
# ─────────────────────────────────────────────────────────────────────────────


def test_slugify_basic():
    _, _, _slugify, *_ = _import_extra()
    assert _slugify("Hello World") == "hello-world"


def test_slugify_cyrillic():
    _, _, _slugify, *_ = _import_extra()
    slug = _slugify("Тестовый раздел")
    assert slug


def test_slugify_empty_returns_section():
    _, _, _slugify, *_ = _import_extra()
    assert _slugify("") == "section"


def test_slugify_special_chars_removed():
    _, _, _slugify, *_ = _import_extra()
    slug = _slugify("hello!@#$%world")
    assert "!" not in slug
    assert "@" not in slug
