#!/usr/bin/env python3
"""Валидация provisioning Grafana (этап E / часть MON-15).

Проверяет каждый monitoring/grafana/*.json:
- корректный JSON и обязательные поля (uid, title, schemaVersion);
- уникальность panel id внутри дашборда;
- gridPos без наездов по X (панели одного ряда не перекрываются);
- каждый target ссылается на известный datasource UID (prometheus|loki);
- non-empty expr для prometheus-панелей.

PromQL-синтаксис дополнительно проверяется promtool'ом: скрипт умеет
эмитить rules-файл со всеми expr (--emit-rules PATH), который прогоняется
через `promtool check rules` в CI (та же механика, что для alert-rules).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

GRAFANA_DIR = Path(__file__).resolve().parent.parent / 'monitoring' / 'grafana'
KNOWN_DATASOURCE_UIDS = {'prometheus', 'loki'}


def fail(dash: str, msg: str) -> None:
    print(f'FAIL [{dash}] {msg}')
    sys.exit(1)


def iter_panels(panels):
    for p in panels:
        yield p
        yield from iter_panels(p.get('panels', []))


def _overlap(a, b):
    """Пересечение прямоугольников сетки (даже частичное — конфликт)."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def check_dashboard(path: Path, rules_out: list[tuple[str, str]]) -> None:
    dash = path.stem
    try:
        d = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        fail(dash, f'invalid JSON: {e}')
    for field in ('uid', 'title', 'schemaVersion'):
        if not d.get(field):
            fail(dash, f'missing required field: {field}')

    panels = list(iter_panels(d.get('panels', [])))
    ids = [p.get('id') for p in panels]
    if len(ids) != len(set(ids)):
        fail(dash, 'duplicate panel ids')

    placed = []
    for p in panels:
        gp = p.get('gridPos')
        if not gp:
            continue
        if not (0 <= gp.get('x', 0) < 24 and gp.get('w', 0) >= 1):
            fail(dash, f"panel {p.get('id')}: gridPos out of 24-col grid: {gp}")
        if gp['x'] + gp['w'] > 24:
            fail(dash, f"panel {p.get('id')}: x+w exceeds 24 cols: {gp}")
        # Конфликт координат: две панели, пересекающиеся на сетке (в т.ч.
        # частично), ломают раскладку — раньше это ускользало от валидатора.
        rect = (gp['x'], gp['y'], gp['x'] + gp['w'], gp['y'] + gp['h'])
        for other_id, other_rect in placed:
            if _overlap(rect, other_rect):
                fail(dash, f"panel {p.get('id')} overlaps panel {other_id}: "
                           f"{gp} vs {other_rect}")
        placed.append((p.get('id'), rect))

        for t in p.get('targets', []):
            ds = t.get('datasource') or {}
            uid = ds.get('uid')
            if uid is not None and uid not in KNOWN_DATASOURCE_UIDS:
                fail(dash, f"panel {p.get('id')}: unknown datasource uid {uid!r}")
            if uid == 'prometheus':
                expr = (t.get('expr') or '').strip()
                if not expr:
                    fail(dash, f"panel {p.get('id')}: empty expr")
                # Имя record — валидный metric name; expr попадёт в promtool
                rules_out.append((f'grafana_{dash}_{p.get("id")}_{t.get("refId", "A")}', expr))


def main() -> None:
    emit_rules = None
    args = sys.argv[1:]
    if '--emit-rules' in args:
        emit_rules = Path(args[args.index('--emit-rules') + 1])

    files = sorted(GRAFANA_DIR.glob('*.json'))
    if not files:
        print('FAIL: no dashboards found')
        sys.exit(1)
    rules: list[tuple[str, str]] = []
    for f in files:
        check_dashboard(f, rules)
    print(f'OK: {len(files)} dashboards validated')

    if emit_rules:
        lines = ['groups:', '  - name: grafana-dashboards-query-syntax',
                 '    interval: 1h', '    rules:']
        for name, expr in rules:
            safe = ''.join(c if c.isalnum() else '_' for c in name)[:180]
            folded = expr.replace('\n', ' ')
            lines += [f'      - record: {safe}', f'        expr: {json.dumps(folded)}']
        emit_rules.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(f'OK: emitted {len(rules)} expressions to {emit_rules}')


if __name__ == '__main__':
    main()
