# Windows CMD Cheat Sheet for AI Agent

## Shell: cmd.exe (NOT bash, NOT PowerShell)

> All commands below are **verified by actual test runs**.

---

## File Reading ✅

```cmd
type C:\full\path\to\file.txt
```

**Prefer the Read tool** — faster, returns line numbers, no encoding issues.

---

## File Deletion ✅

```cmd
del C:\full\path\to\file.txt
```

Recursive folder delete:
```cmd
rmdir /S /Q C:\full\path\to\folder
```

---

## Directory Navigation ⚠️

```cmd
cd /d C:\full\path\to\dir
```

**WARNING (tested):** `cd /d "quoted\path" && next_command` — FAILS with error.
Use paths **without quotes** when chaining with `&&`:
```cmd
cd /d C:\Users\admin\project && dir /B *.md
```

---

## Directory Listing ✅

```cmd
dir C:\full\path\to\dir
dir /B C:\path\to\dir
```

(`/B` — bare format, names only)

---

## Command Chaining ✅

| Operator | Meaning | Verified |
|----------|---------|---------|
| `&&` | Run next only if previous succeeded | ✅ |
| `\|\|` | Run next only if previous failed | — |
| `&` | Run next regardless | — |
| `;` | **DOES NOTHING — never use** | ✅ |

**WARNING (tested):** `&&` combined with **quoted paths** in the same command often breaks.
Safest: chain only simple commands, or use separate Bash tool calls.

---

## Output Redirection ⚠️

```cmd
echo text > C:\path\file.txt
```

**WARNING (tested):** `echo text > "quoted path"` — FAILS.
Do NOT use quotes around the redirect target:
```cmd
echo test > C:\path\file.txt
```

---

## Environment Variables ✅

```cmd
echo %USERPROFILE%
echo %PATH%
```

NOT `$VAR` — that's bash.

---

## Create Directory ✅

```cmd
mkdir C:\path\to\new\dir\sub1\sub2
```

Creates all intermediate directories automatically — no `-p` flag needed.

---

## Copy / Move

```cmd
copy source.txt dest.txt
xcopy /E /I sourceDir destDir
move source dest
```

---

## Docker on Windows ✅

```cmd
docker compose ps
docker compose up -d
docker compose down
docker compose down && docker compose up -d
docker compose logs --tail=50 backend
docker compose logs -f backend
```

### Выполнение команд внутри контейнера ✅

```cmd
docker compose exec backend python --version
docker compose exec backend alembic current
docker compose exec backend alembic upgrade head
docker compose exec backend python -m pytest
docker compose exec backend ls /app
docker compose exec postgres psql -U portal -d portal -c \dt
docker compose exec redis redis-cli ping
```

**ВАЖНО (проверено):**
- `docker compose exec backend bash -c "команда"` — **ЛОМАЕТСЯ** ❌
- `docker compose exec backend bash -c 'команда'` — **ТОЖЕ ЛОМАЕТСЯ** ❌
- `docker compose exec backend python -c "код"` — **ЛОМАЕТСЯ** ❌
  CMD съедает кавычки, контейнер получает битую строку.

**Правило:** передавай команды **без `sh -c` обёртки** — напрямую:
```cmd
docker compose exec backend ls /app
docker compose exec backend python --version
docker compose exec backend python -m pytest
```

**Если нужно выполнить Python-код** — создай файл через Write tool в смонтированном volume,
затем запусти его:
```
(Write tool: upload_data\kb\_script.py)
docker compose exec backend python /data/kb/_script.py
del upload_data\kb\_script.py
```

Смонтированные volumes backend (хост → контейнер):
- `upload_data\kb` → `/data/kb`
- `upload_data\avatars` → `/data/avatars`
- `system_data\settings` → `/data/settings`

---

## Strings

- Use **double quotes** `"text"` — NEVER single quotes `'text'`
- Quotes around paths work for `type`, `del`, `rmdir`, `mkdir`
- Quotes around paths **break** when combined with `&&` or `>`

---

## Critical Rules

1. **Always use absolute paths** — especially before `del` or `rmdir`
2. **Never use Unix commands**: `cat`, `grep`, `find`, `rm`, `cp`, `mv`, `chmod`, `ls`
3. **Never use `;`** as command separator — it does nothing
4. **Never use `-flag`** Unix-style flags
5. **No `$VAR`** — use `%VAR%`
6. Use **Grep tool** instead of running `rg`/`grep` as Bash commands
7. Use **Read tool** instead of `type` — no encoding issues, has line numbers
8. **Avoid mixing quotes + `&&` + `>`** in one command — use separate Bash calls instead
