#!/usr/bin/env bash
# Bootstrap applyforme on a fresh Ubuntu EC2 (Amazon Linux: adapt package names).
# Usage (as ubuntu, from the repo root you cloned to /opt/applyforme):
#   sudo bash deploy/ec2/setup.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/applyforme}"
USER_NAME="${SUDO_USER:-ubuntu}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo"; exit 1
fi

apt-get update -y
apt-get install -y python3 python3-venv python3-pip git nginx curl

# Node 20
if ! command -v node >/dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

# Playwright OS deps (Chromium)
cd "$APP_DIR"
sudo -u "$USER_NAME" python3 -m venv .venv
sudo -u "$USER_NAME" .venv/bin/pip install -U pip
sudo -u "$USER_NAME" .venv/bin/pip install -r requirements.txt
sudo -u "$USER_NAME" .venv/bin/playwright install-deps chromium || true
sudo -u "$USER_NAME" .venv/bin/playwright install chromium

if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  # Generate secrets
  SECRET=$(openssl rand -hex 32)
  AUTH=$(openssl rand -hex 32)
  sed -i "s/^# PIPELINE_WEBHOOK_SECRET=.*/PIPELINE_WEBHOOK_SECRET=$SECRET/" "$APP_DIR/.env" || true
  grep -q '^PIPELINE_WEBHOOK_SECRET=' "$APP_DIR/.env" || echo "PIPELINE_WEBHOOK_SECRET=$SECRET" >> "$APP_DIR/.env"
  grep -q '^AUTH_SECRET=' "$APP_DIR/.env" || echo "AUTH_SECRET=$AUTH" >> "$APP_DIR/.env"
  grep -q '^SCHEDULE_RUN=' "$APP_DIR/.env" || echo "SCHEDULE_RUN=0 */4 * * *" >> "$APP_DIR/.env"
  grep -q '^SCHEDULE_INBOX=' "$APP_DIR/.env" || echo "SCHEDULE_INBOX=30 */6 * * *" >> "$APP_DIR/.env"
  grep -q '^PIPELINE_WORKER_URL=' "$APP_DIR/.env" || echo "PIPELINE_WORKER_URL=http://127.0.0.1:8787" >> "$APP_DIR/.env"
  echo "Wrote $APP_DIR/.env — edit OPENAI_API_KEY, APP_URL, Google OAuth, then restart services."
fi

cd "$APP_DIR/dashboard"
sudo -u "$USER_NAME" npm ci || sudo -u "$USER_NAME" npm install
sudo -u "$USER_NAME" npm run build

install -m 644 "$APP_DIR/deploy/ec2/applyforme-worker.service" /etc/systemd/system/
install -m 644 "$APP_DIR/deploy/ec2/applyforme-web.service" /etc/systemd/system/
# Fix User= in units if needed
sed -i "s/^User=.*/User=$USER_NAME/" /etc/systemd/system/applyforme-worker.service
sed -i "s/^User=.*/User=$USER_NAME/" /etc/systemd/system/applyforme-web.service
sed -i "s|/opt/applyforme|$APP_DIR|g" /etc/systemd/system/applyforme-worker.service
sed -i "s|/opt/applyforme|$APP_DIR|g" /etc/systemd/system/applyforme-web.service

systemctl daemon-reload
systemctl enable --now applyforme-worker applyforme-web

if [[ -f "$APP_DIR/deploy/ec2/nginx.conf" ]]; then
  cp "$APP_DIR/deploy/ec2/nginx.conf" /etc/nginx/sites-available/applyforme
  ln -sf /etc/nginx/sites-available/applyforme /etc/nginx/sites-enabled/applyforme
  rm -f /etc/nginx/sites-enabled/default
  nginx -t && systemctl reload nginx
fi

echo ""
echo "=== applyforme EC2 ready ==="
echo "Worker:  systemctl status applyforme-worker"
echo "Web:     systemctl status applyforme-web"
echo "Health:  curl -s http://127.0.0.1:8787/health"
echo "Trigger: curl -X POST http://127.0.0.1:8787/hooks/run \\"
echo "           -H \"Authorization: Bearer \$PIPELINE_WEBHOOK_SECRET\" -H 'Content-Type: application/json' -d '{}'"
echo "Public:  POST https://YOUR_DOMAIN/api/pipeline/webhook  {\"stage\":\"run\"}"
echo "Open security group: 80/443 only. Do NOT expose port 8787 publicly."
