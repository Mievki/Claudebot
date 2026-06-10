#!/usr/bin/env bash
# Installatie van de TEMA-bot op een verse Ubuntu-server (bv. Hetzner CX23).
# Idempotent: opnieuw draaien = updaten. Draai als root: sudo bash install.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Mievki/Claudebot.git}"
APP_DIR=/opt/tema-bot
BOT_DIR="$APP_DIR/tema-bot"

if [ "$(id -u)" -ne 0 ]; then
    echo "FOUT: draai als root (sudo bash install.sh)" >&2
    exit 1
fi

echo "==> Pakketten installeren"
apt-get update -qq
apt-get install -y -qq git python3 python3-venv

echo "==> Systeemgebruiker 'temabot' (geen login-shell)"
id -u temabot >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin temabot

echo "==> Code ophalen naar $APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull --ff-only
else
    git clone "$REPO_URL" "$APP_DIR"
fi

echo "==> Python-venv + dependencies"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$BOT_DIR/requirements.txt"

echo "==> Data-map en .env"
mkdir -p "$BOT_DIR/data"
if [ ! -f "$BOT_DIR/.env" ]; then
    cp "$BOT_DIR/.env.example" "$BOT_DIR/.env"
    echo "    NIEUW: $BOT_DIR/.env aangemaakt vanaf .env.example - VUL DEZE IN"
fi
chown -R temabot:temabot "$APP_DIR"
chmod 600 "$BOT_DIR/.env"

echo "==> systemd-units installeren"
cp "$BOT_DIR/deploy/tema-bot.service" \
   "$BOT_DIR/deploy/tema-bot.timer" \
   "$BOT_DIR/deploy/tema-telegram.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now tema-bot.timer
systemctl enable tema-telegram.service

cat <<'EOF'

KLAAR. Volgende stappen:
  1. nano /opt/tema-bot/tema-bot/.env       (MODE, OKX-keys, TELEGRAM_*)
  2. systemctl start tema-telegram.service  (listener aan; check met /status in Telegram)
  3. systemctl start tema-bot.service       (eenmalige testrun, hoeft niet te wachten op 00:02)
  4. journalctl -u tema-bot -n 50           (logs van de trade-job)
     journalctl -u tema-telegram -f         (logs van de listener)
De timer draait daarna elke dag om 00:02 UTC. `systemctl list-timers tema-bot.timer`
EOF
