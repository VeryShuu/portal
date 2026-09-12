#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Cleaning __pycache__ directories..."
find "$REPO_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo "Cleaning *.pyc / *.pyo files..."
find "$REPO_ROOT" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete 2>/dev/null || true

echo "Cleaning .pytest_cache directories..."
find "$REPO_ROOT" -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true

echo "Cleaning .playwright-mcp/ session artefacts..."
rm -rf "$REPO_ROOT/.playwright-mcp"

echo "Done."
