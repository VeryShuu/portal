# Нагрузочное тестирование (k6)

Цели по ТЗ §7:
- 300 одновременных сессий
- p95 < 2 сек
- поиск < 1 сек

## Запуск

```bash
# Smoke (быстрая проверка работоспособности скриптов)
k6 run -e BASE_URL=http://localhost:8000 load/smoke.js

# Базовая нагрузка — 50 VU, 1 минута
k6 run -e BASE_URL=http://localhost:8000 load/baseline.js

# Полный сценарий — рамп до 300 VU, 10 минут
k6 run -e BASE_URL=http://localhost:8000 -e ADMIN_EMAIL=... -e ADMIN_PASSWORD=... load/portal-load.js

# Нагрузка на поиск (требование <1 сек p95)
k6 run -e BASE_URL=http://localhost:8000 load/search.js
```

## CI

В пайплайне запускается только `smoke.js` для регрессионной проверки (бюджет ~30 сек).
Полные сценарии запускаются вручную перед релизом.
