"""Generate Markdown API documentation from the FastAPI OpenAPI spec.

Usage (from ./backend/):
    python -m scripts.generate_api_contracts_doc
    python -m scripts.generate_api_contracts_doc --output ../docs/api-contracts.generated.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "x" * 32)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _resolve_ref(ref: str, spec: dict[str, Any]) -> dict[str, Any]:
    parts = ref.lstrip("#/").split("/")
    node: Any = spec
    for part in parts:
        node = node[part]
    return node


def _schema_summary(schema: dict[str, Any], spec: dict[str, Any], depth: int = 0) -> str:
    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        return f"`{ref_name}`"
    if "allOf" in schema and len(schema["allOf"]) == 1:
        return _schema_summary(schema["allOf"][0], spec, depth)
    typ = schema.get("type", "")
    if typ == "array":
        items = schema.get("items", {})
        return f"array of {_schema_summary(items, spec, depth)}"
    if typ == "object":
        props = schema.get("properties", {})
        if not props:
            return "object"
        if depth >= 1:
            return f"object ({', '.join(props.keys())})"
        parts = []
        for k, v in props.items():
            parts.append(f"`{k}`: {_schema_summary(v, spec, depth + 1)}")
        return "{ " + ", ".join(parts) + " }"
    return typ or "any"


def _params_table(params: list[dict[str, Any]], spec: dict[str, Any]) -> str:
    if not params:
        return ""
    lines = ["| Name | In | Type | Required | Description |"]
    lines.append("|------|----|------|----------|-------------|")
    for p in params:
        if "$ref" in p:
            p = _resolve_ref(p["$ref"], spec)
        name = p.get("name", "")
        location = p.get("in", "")
        required = "✓" if p.get("required") else ""
        desc = p.get("description", "").replace("\n", " ")
        schema = p.get("schema", {})
        if "$ref" in schema:
            typ = schema["$ref"].split("/")[-1]
        else:
            typ = schema.get("type", "any")
            enum = schema.get("enum")
            if enum:
                typ += f" ({', '.join(str(e) for e in enum)})"
        lines.append(f"| `{name}` | {location} | `{typ}` | {required} | {desc} |")
    return "\n".join(lines)


def _request_body_section(rb: dict[str, Any], spec: dict[str, Any]) -> str:
    if not rb:
        return ""
    lines = ["**Request Body**\n"]
    content = rb.get("content", {})
    for media_type, media in content.items():
        schema = media.get("schema", {})
        if "$ref" in schema:
            resolved = _resolve_ref(schema["$ref"], spec)
            ref_name = schema["$ref"].split("/")[-1]
            lines.append(f"Content-Type: `{media_type}` — schema: `{ref_name}`\n")
            props = resolved.get("properties", {})
            required_fields = resolved.get("required", [])
            if props:
                lines.append("| Field | Type | Required | Description |")
                lines.append("|-------|------|----------|-------------|")
                for field, fschema in props.items():
                    req = "✓" if field in required_fields else ""
                    desc = fschema.get("description", "").replace("\n", " ")
                    ftype = _schema_summary(fschema, spec)
                    lines.append(f"| `{field}` | {ftype} | {req} | {desc} |")
        else:
            lines.append(f"Content-Type: `{media_type}`\n")
            summary = _schema_summary(schema, spec)
            lines.append(f"Schema: {summary}")
    return "\n".join(lines)


def _responses_table(responses: dict[str, Any], spec: dict[str, Any]) -> str:
    lines = ["| Status | Description | Schema |"]
    lines.append("|--------|-------------|--------|")
    for code, resp in sorted(responses.items()):
        if "$ref" in resp:
            resp = _resolve_ref(resp["$ref"], spec)
        desc = resp.get("description", "").replace("\n", " ")
        schema_str = ""
        content = resp.get("content", {})
        for _media_type, media in content.items():
            schema = media.get("schema", {})
            schema_str = _schema_summary(schema, spec)
            break
        lines.append(f"| {code} | {desc} | {schema_str} |")
    return "\n".join(lines)


def generate(spec: dict[str, Any], output: Path | None) -> None:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    paths = spec.get("paths", {})

    by_tag: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    untagged: list[tuple[str, str, dict[str, Any]]] = []

    http_methods = ["get", "post", "put", "patch", "delete", "head", "options"]

    for path, path_item in sorted(paths.items()):
        for method in http_methods:
            op = path_item.get(method)
            if not op:
                continue
            tags = op.get("tags", [])
            entry = (method.upper(), path, op)
            if tags:
                for tag in tags:
                    by_tag.setdefault(tag, []).append(entry)
            else:
                untagged.append(entry)

    out: list[str] = [
        "<!-- AUTO-GENERATED — do not edit manually. Run: cd backend && python -m scripts.generate_api_contracts_doc --output ../docs/api-contracts.generated.md -->",
        f"<!-- Generated: {now} -->",
        "",
        "# API Contracts (auto-generated)",
        "",
        "> Generated from FastAPI OpenAPI spec.  \n> Source of truth: `./docs/api-contracts.generated.md` (auto) and `./docs/api-contracts.md` (curated).  \n> Base URL: `/api/v1/`",
        "",
        "---",
        "",
        "## Table of Contents",
        "",
    ]

    all_tags = sorted(by_tag.keys())
    for tag in all_tags:
        anchor = tag.lower().replace(" ", "-").replace("/", "")
        out.append(f"- [{tag}](#{anchor})")
    if untagged:
        out.append("- [Untagged](#untagged)")

    out.append("")
    out.append("---")
    out.append("")

    for tag in all_tags:
        anchor = tag.lower().replace(" ", "-").replace("/", "")
        out.append(f"## {tag}\n")
        entries = by_tag[tag]
        for method, path, op in entries:
            summary = op.get("summary", "")
            deprecated = " *(deprecated)*" if op.get("deprecated") else ""
            out.append(f"### `{method} {path}`{deprecated}\n")
            if summary:
                out.append(f"**{summary}**\n")
            if op.get("description"):
                out.append(op["description"].strip() + "\n")

            params = op.get("parameters", [])
            params_md = _params_table(params, spec)
            if params_md:
                out.append("**Parameters**\n")
                out.append(params_md + "\n")

            rb = op.get("requestBody", {})
            rb_md = _request_body_section(rb, spec)
            if rb_md:
                out.append(rb_md + "\n")

            responses = op.get("responses", {})
            out.append("**Responses**\n")
            out.append(_responses_table(responses, spec) + "\n")

        out.append("---")
        out.append("")

    if untagged:
        out.append("## Untagged\n")
        for method, path, op in untagged:
            summary = op.get("summary", "")
            out.append(f"### `{method} {path}`\n")
            if summary:
                out.append(f"**{summary}**\n")
        out.append("---")
        out.append("")

    content = "\n".join(out)

    if output:
        output.write_text(content, encoding="utf-8")
        size = output.stat().st_size
        total_ops = sum(len(v) for v in by_tag.values()) + len(untagged)
        print(
            f"API contracts doc written: {output} ({size} bytes, {len(paths)} paths, {total_ops} operations)",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate API contracts Markdown from FastAPI OpenAPI spec")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output file path (default: ../docs/api-contracts.generated.md)",
    )
    parser.add_argument(
        "--openapi-json",
        type=Path,
        default=None,
        help="Use existing openapi.json instead of importing the app (faster)",
    )
    args = parser.parse_args()

    if args.output is None:
        args.output = Path(__file__).resolve().parents[2] / "docs" / "api-contracts.generated.md"

    if args.openapi_json and args.openapi_json.exists():
        spec = json.loads(args.openapi_json.read_text(encoding="utf-8"))
    else:
        from app.main import app  # type: ignore[import-not-found]
        spec = app.openapi()

    generate(spec, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
