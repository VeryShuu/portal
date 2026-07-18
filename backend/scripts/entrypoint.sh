#!/bin/sh
set -e

# Recursive chown of /data is expensive on every restart (large photo trees,
# KB attachments, NC mirror metadata). It only matters once, after the volume
# is first mounted with host-owned UIDs. After that, all writes happen as the
# `portal` user anyway, so ownership stays correct.
#
# We mark the volume with a sentinel file once chown has succeeded; subsequent
# starts skip the recursive walk entirely. To force a re-chown (e.g. after a
# manual operation that left files owned by root), delete /data/.chowned and
# restart the container.
SENTINEL=/data/.chowned

# Self-healing: даже при существующем sentinel права могут «съехать», если какой-
# то процесс от root (например ``docker compose exec backend python ...`` без gosu,
# или worker со сломанным entrypoint) создал в /data файлы/папки от root:root.
# Тогда portal-процесс получит PermissionError при попытке создать вложенную
# папку (как в баге helpdesk TKT-2/inline: корень /data/helpdesk writable, а
# вложенная TKT-2 — нет). Проверка ``test -w`` на корневых папках это пропустит,
# поэтому ищем **любой** файл/папку с uid=0 через ``find -quit`` (остановка на
# первом совпадении — дёшево в нормальном случае, когда root-файлов нет).
#
# Срабатывает только при реальной поломке прав — тогда один ``chown -R /data``
# чинит всё за раз (это медленно на больших photo-деревьях, но бывает редко).
needs_chown=0
if [ ! -f "$SENTINEL" ]; then
    # Первый старт (нет sentinel) — обязательный полный chown.
    needs_chown=1
else
    # Sentinel есть — ищем root-файлы быстрым find (прерывается на первом).
    # ``-path /data/.chowned -prune`` исключает сам sentinel из поиска (он может
    # быть root-овским как fallback, и это норма — не повод запускать chown).
    if find /data -path /data/.chowned -prune -o -uid 0 -print -quit 2>/dev/null \
            | grep -q .; then
        needs_chown=1
    fi
fi

if [ "$needs_chown" = "1" ]; then
    chown -R portal:portal /data 2>/dev/null || true
    # Use the portal user so the sentinel itself is not root-owned.
    su -s /bin/sh -c "touch '$SENTINEL'" portal 2>/dev/null \
        || touch "$SENTINEL" 2>/dev/null \
        || true
fi

exec gosu portal "$@"
