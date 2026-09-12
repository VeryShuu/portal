#!/usr/bin/env bash
# =============================================================================
# forgejo-runner-install.sh — установка и регистрация forgejo-runner на CI-сервере.
#
# Запускать НА сервере, где будет жить runner (по нашему решению — хост forgejo.mage.ru).
# Требования ОС: Linux + systemd + Docker (демон должен работать — job'ы используют его
# через сокет). Скрипт пишет в /usr/local/bin, /etc/forgejo-runner, /etc/systemd/system.
#
# Usage (на сервере):
#   # 1. Положить рядом config (из репозитория):
#   #    scripts/forgejo-runner-config.yaml → /etc/forgejo-runner/config.yaml
#   # 2. Задать registration token (instance-scope, выдаётся админом):
#   export FORGEJO_RUNNER_TOKEN='<REGISTRATION_TOKEN>'
#   # 3. (опц.) переопределить URL инстанса/имя runner'а:
#   export FORGEJO_URL='https://forgejo.mage.ru'
#   export RUNNER_NAME="forgejo-runner-1"
#   # 4. Запустить:
#   sudo -E bash scripts/forgejo-runner-install.sh
#
# После установки: статус — `systemctl status forgejo-runner`,
# в UI инстанса бегун появится в Site Administration → Actions → Runners.
# =============================================================================
set -euo pipefail

red()    { printf '\033[0;31m%s\033[0m\n' "$*" >&2; }
green()  { printf '\033[0;32m%s\033[0m\n' "$*"; }
die()    { red "✗ $*"; exit 1; }

FORGEJO_URL="${FORGEJO_URL:-https://forgejo.mage.ru}"
RUNNER_NAME="${RUNNER_NAME:-$(hostname)}"
CONFIG_DEST="${CONFIG_DEST:-/etc/forgejo-runner/config.yaml}"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"
: "${FORGEJO_RUNNER_TOKEN:?Требуется env FORGEJO_RUNNER_TOKEN (registration token, instance-scope)}"

[[ "$(id -u)" -eq 0 ]] || die "Запустите через sudo: sudo -E bash $0"
command -v docker >/dev/null || die "Docker не установлен. forgejo-runner требует демон Docker."
systemctl is-active --quiet docker || die "Docker-демон не запущен: sudo systemctl enable --now docker"
command -v curl >/dev/null || die "curl не установлен."
command -v jq   >/dev/null || die "jq не установлен."

echo "→ Сервер: ${FORGEJO_URL} | runner: ${RUNNER_NAME}"

# ── 1. Скачать свежий forgejo-runner из code.forgejo.org ──────────────────────
RUNNER_VER="${RUNNER_VER:-$(curl -fsSL https://code.forgejo.org/api/v1/repos/forgejo/runner/releases/latest | jq -r .tag_name)}"
[[ "$RUNNER_VER" != "null" && -n "$RUNNER_VER" ]] || die "Не удалось узнать версию forgejo-runner."
echo "→ Версия forgejo-runner: ${RUNNER_VER}"

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64)  ASSET_ARCH="amd64" ;;
  aarch64|arm64) ASSET_ARCH="arm64" ;;
  *) die "Неподдерживаемая архитектура: $ARCH" ;;
esac
# Имя ассета у forgejo-runner: forgejo-runner-<ver_without_v>-linux-<arch>(.exe для win)
VER_NUM="${RUNNER_VER#v}"
URL="https://code.forgejo.org/forgejo/runner/releases/download/${RUNNER_VER}/forgejo-runner-${VER_NUM}-linux-${ASSET_ARCH}"
echo "→ Скачиваю: ${URL}"
curl -fsSL "$URL" -o /tmp/forgejo-runner
chmod +x /tmp/forgejo-runner
install -m 0755 /tmp/forgejo-runner "${INSTALL_DIR}/forgejo-runner"
green "✓ Бинарник установлен: ${INSTALL_DIR}/forgejo-runner"
"${INSTALL_DIR}/forgejo-runner" --version

# ── 2. Конфиг ─────────────────────────────────────────────────────────────────
mkdir -p "$(dirname "$CONFIG_DEST")"
if [[ ! -f "$CONFIG_DEST" ]]; then
  red "✗ Конфиг не найден: ${CONFIG_DEST}."
  red "  Скопируйте scripts/forgejo-runner-config.yaml (из репо portal) туда:"
  red "    sudo mkdir -p $(dirname "$CONFIG_DEST")"
  red "    sudo cp forgejo-runner-config.yaml ${CONFIG_DEST}"
  red "  Затем перезапустите этот скрипт."
  exit 1
fi
green "✓ Конфиг на месте: ${CONFIG_DEST}"

# ── 3. Регистрация ────────────────────────────────────────────────────────────
# Лейблы ДОЛЖНЫ мэтчить runs-on: ubuntu-latest во всех .forgejo/workflows/*.
# (дублируют те же значения из config.yaml — register их принимает здесь)
LABELS="ubuntu-latest=docker://catthehacker/ubuntu:act-22.04,ubuntu-22.04=docker://catthehacker/ubuntu:act-22.04"
RUNNER_HOME="${RUNNER_HOME:-/var/lib/forgejo-runner}"
mkdir -p "$RUNNER_HOME"

echo "→ Регистрирую runner «${RUNNER_NAME}»…"
# --no-interactive + --token + --instance + --name + --labels.
# Файл .runner (учётка бегуна) пишется в RUNNER_HOME.
(
  cd "$RUNNER_HOME"
  "${INSTALL_DIR}/forgejo-runner" register \
    --no-interactive \
    --instance "$FORGEJO_URL" \
    --token "$FORGEJO_RUNNER_TOKEN" \
    --name "$RUNNER_NAME" \
    --labels "$LABELS"
)
green "✓ Runner зарегистрирован (home: ${RUNNER_HOME})"

# ── 4. systemd unit ───────────────────────────────────────────────────────────
cat > /etc/systemd/system/forgejo-runner.service <<EOF
[Unit]
Description=Forgejo Runner (portal CI)
After=network-online.target docker.service
Wants=network-online.target docker.service
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=${RUNNER_HOME}
ExecStart=${INSTALL_DIR}/forgejo-runner --config ${CONFIG_DEST} daemon
Restart=on-failure
RestartSec=5
# Лимиты — portal-CI билдит Docker-образы (память/диск):
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now forgejo-runner
sleep 2
systemctl is-active --quiet forgejo-runner && green "✓ forgejo-runner запущен" \
  || { red "✗ forgejo-runner не стартовал — логи:"; journalctl -u forgejo-runner -n 50 --no-pager; exit 1; }

echo
green "✓ Готово. Проверьте в UI: ${FORGEJO_URL}/-/admin/actions/runners"
echo "   Логи: journalctl -u forgejo-runner -f"
echo "   Тестовый прогон: толкните PR в mage/portal — job подхватится лейблом ubuntu-latest."
