#!/usr/bin/env bash
# scripts/release.sh — создать и запушить релизный тег v1.2.3 (ADR-047).
#
# Semver-lock прода: прод обязан пиниться к релизному тегу. Этот скрипт —
# эргономичная обёртка над `git tag -a ... && git push origin <tag>`, которая
# валидирует формат и состояние репозитория ДО того, как тег уйдёт в origin
# (и запустит CI publish-images + deploy-bundle).
#
# CI (job validate-release-tag) дублирует проверку формата — defense-in-depth,
# на случай если кто-то тегнёт в обход этого скрипта.
#
# Usage:
#   ./scripts/release.sh 1.2.3         # → v1.2.3
#   ./scripts/release.sh v1.2.3        # → v1.2.3 (с/без v — оба ок)
#   ./scripts/release.sh 1.2.3-rc1     # → v1.2.3-rc1 (release candidate)
#
# После зелёного CI: на проде выставить IMAGE_TAG=v1.2.3 в .env → setup.sh п.6.
set -euo pipefail

# ─── Хелперы ──────────────────────────────────────────────────────────────────
red()    { printf '\033[0;31m%s\033[0m\n' "$*"; }
green()  { printf '\033[0;32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[1;33m%s\033[0m\n' "$*"; }
dim()    { printf '\033[2m%s\033[0m\n' "$*"; }
die()    { red "✗ $*"; exit 1; }
ok()     { green "✓ $*"; }

# ─── Валидация аргументов ─────────────────────────────────────────────────────
if [[ $# -ne 1 ]]; then
    cat >&2 <<'USAGE'
Usage: ./scripts/release.sh <version>

  version — semver: 1.2.3 или v1.2.3, опц. -rc1 (1.2.3-rc1)

Примеры:
  ./scripts/release.sh 1.2.3
  ./scripts/release.sh v1.2.3
  ./scripts/release.sh 1.2.3-rc1
USAGE
    exit 2
fi

raw="$1"
# Нормализуем: убираем ведущее 'v', добавим обратно перед валидацией.
ver="${raw#v}"
tag="v${ver}"

# Regex совпадает с CI (validate-release-tag): X.Y.Z с опц. -rcN (N — номер).
# Формат: v1.2.3 или v1.2.3-rc1. Ведущие нули в rc-номере допустимы (rc01, rc10).
if [[ ! "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-rc[0-9]+)?$ ]]; then
    die "Некорректный semver: '${raw}'. Допустимо: 1.2.3 или 1.2.3-rc1 (X.Y.Z)."
fi
ok "Semver формат: ${tag}"

# ─── Проверки репозитория ─────────────────────────────────────────────────────
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" \
    || die "Не в git-репозитории. Запускайте из клона portal."
cd "$REPO_ROOT"

# 1. Чистое дерево — незакоммиченные изменения не должны уехать в релиз.
if [[ -n "$(git status --porcelain)" ]]; then
    echo >&2
    yellow "Рабочее дерево не чистое:"
    git status --short >&2
    echo >&2
    die "Закоммитьте или stash'ните изменения перед релизом."
fi
ok "Рабочее дерево: чистое"

# 2. HEAD синхронизирован с origin/main (защита от релиза локальных коммитов).
git fetch origin --quiet
local_head=$(git rev-parse HEAD)
remote_main=$(git rev-parse origin/main 2>/dev/null) \
    || die "origin/main не найден. Проверьте remote: git remote -v"
if [[ "$local_head" != "$remote_main" ]]; then
    die "HEAD (${local_head:0:7}) ≠ origin/main (${remote_main:0:7})." \
        "Сделайте git pull / push, чтобы синхронизироваться с main."
fi
ok "HEAD = origin/main (${local_head:0:7})"

# 3. Тег ещё не существует (защита от перезаписи).
if git rev-parse "$tag" >/dev/null 2>&1; then
    die "Тег ${tag} уже существует: $(git rev-parse "$tag" | cut -c1-7)." \
        "Семантические версии не переиспользуются — выберите следующий номер."
fi
ok "Тег ${tag}: свободен"

# ─── Создание и пуш ───────────────────────────────────────────────────────────
echo
echo "Создаю annotated tag ${tag} на коммите ${local_head:0:7}..."
git tag -a "$tag" -m "Release ${tag}"
ok "Локальный тег создан"

echo
echo "Пушу тег в origin (это запустит CI: publish-images + deploy-bundle)..."
git push origin "$tag"
ok "Тег запушен"

# ─── Что дальше ────────────────────────────────────────────────────────────────
echo
green "✓ Релиз ${tag} инициирован."
echo
dim "Дальше:"
dim "  1. Дождаться зелёного CI (publish-images + deploy-bundle):"
dim "       https://github.com/VeryShuu/portal/actions"
dim "  2. Проверить, что tarball появился в Release:"
dim "       gh release view ${tag} --repo VeryShuu/portal"
dim "  3. На проде выставить IMAGE_TAG=${tag} в .env:"
dim "       ./setup.sh   # → п.6 «Обновить Production»"
echo
dim "Откат (если что-то пошло не так):"
dim "  IMAGE_TAG=<предыдущий-релиз> в .env на проде → setup.sh п.6."
dim "  Тег в origin НЕ удалять (история)."
