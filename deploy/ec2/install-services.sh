#!/usr/bin/env bash
# Install / re-install ONLY the systemd units, then enable + start them.
#
# Use this when `sudo bash deploy/ec2/setup.sh` stopped early (pip, Playwright,
# or `npm run build` failed) and `systemctl status` says "Unit ... could not be found".
#
#   sudo bash deploy/ec2/install-services.sh
#
# It is safe to re-run. If Python deps or the dashboard build are missing it
# installs the units but refuses to enable them and prints the exact commands.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/applyforme}"
# WORKER_ONLY=1 installs only the Python worker (no dashboard/Node checks).
WORKER_ONLY="${WORKER_ONLY:-0}"

if [[ -n "${APPLYFORME_USER:-}" ]]; then
  USER_NAME="$APPLYFORME_USER"
elif id -u ec2-user >/dev/null 2>&1; then
  USER_NAME=ec2-user
elif id -u ubuntu >/dev/null 2>&1; then
  USER_NAME=ubuntu
else
  USER_NAME="${SUDO_USER:-root}"
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo bash deploy/ec2/install-services.sh" >&2
  exit 1
fi
if [[ ! -d "$APP_DIR" ]]; then
  echo "Missing $APP_DIR — clone the repo there first (see deploy/ec2/PUSH.md)" >&2
  exit 1
fi

NPM_BIN="$(command -v npm || true)"
if [[ -z "$NPM_BIN" ]]; then
  NPM_BIN=/usr/bin/npm
fi

install -m 644 "$APP_DIR/deploy/ec2/applyforme-worker.service" /etc/systemd/system/
sed -i "s/^User=.*/User=$USER_NAME/" /etc/systemd/system/applyforme-worker.service
sed -i "s|/opt/applyforme|$APP_DIR|g" /etc/systemd/system/applyforme-worker.service

if [[ "$WORKER_ONLY" == "1" ]]; then
  systemctl disable --now applyforme-web 2>/dev/null || true
  rm -f /etc/systemd/system/applyforme-web.service
else
  install -m 644 "$APP_DIR/deploy/ec2/applyforme-web.service" /etc/systemd/system/
  sed -i "s/^User=.*/User=$USER_NAME/" /etc/systemd/system/applyforme-web.service
  sed -i "s|/opt/applyforme|$APP_DIR|g" /etc/systemd/system/applyforme-web.service
  sed -i "s|/usr/bin/npm|$NPM_BIN|g" /etc/systemd/system/applyforme-web.service
fi
systemctl daemon-reload

echo "Units installed for user=$USER_NAME at $APP_DIR"

missing=0
node_ok() {
  command -v node >/dev/null 2>&1 || return 1
  local v major minor
  v="$(node -v 2>/dev/null | sed 's/^v//')"
  major="${v%%.*}"
  minor="${v#*.}"; minor="${minor%%.*}"
  [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ ]] || return 1
  (( major > 22 || (major == 22 && minor >= 14) ))
}
if [[ "$WORKER_ONLY" != "1" ]]; then
  if ! node_ok || ! command -v npm >/dev/null 2>&1; then
    echo "! Node.js 22.14+ and npm are required (found $(node -v 2>/dev/null || echo none))."
    echo "  Node 20 causes better-sqlite3 13 to segfault on the first database open."
    missing=1
  fi
fi
if [[ ! -f "$APP_DIR/.env" ]]; then
  echo "! Missing $APP_DIR/.env — copy .env.example and set OPENAI_API_KEY."
  missing=1
fi
if [[ -f "$APP_DIR/.env" ]]; then
  if ! grep -qE '^PIPELINE_WEBHOOK_SECRET=.+' "$APP_DIR/.env"; then
    echo "! WARNING: PIPELINE_WEBHOOK_SECRET is empty — /hooks/* will return 401."
    echo "  Fix: echo \"PIPELINE_WEBHOOK_SECRET=\$(openssl rand -hex 32)\" >> $APP_DIR/.env"
    echo "  Then: sudo systemctl restart applyforme-worker"
  fi
  if ! grep -qE '^AUTH_SECRET=.+' "$APP_DIR/.env"; then
    echo "! WARNING: AUTH_SECRET is empty — sessions/auth may not work."
  fi
fi
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
  echo "! Missing $APP_DIR/.venv/bin/python — Python dependencies are not installed."
  missing=1
elif ! sudo -u "$USER_NAME" env PYTHONPATH="$APP_DIR" "$APP_DIR/.venv/bin/python" -c 'import applyforme.cli' >/dev/null 2>&1; then
  echo "! The venv exists but 'import applyforme.cli' fails — pip install did not finish."
  missing=1
elif ! sudo -u "$USER_NAME" env PYTHONPATH="$APP_DIR" "$APP_DIR/.venv/bin/python" -m compileall -q "$APP_DIR/applyforme" >/dev/null 2>&1; then
  echo "! Python syntax check failed — fix the traceback before starting the worker."
  echo "  Run: $APP_DIR/.venv/bin/python -m compileall -q $APP_DIR/applyforme"
  missing=1
fi
if [[ "$WORKER_ONLY" != "1" && ! -f "$APP_DIR/dashboard/.next/BUILD_ID" ]]; then
  echo "! Missing $APP_DIR/dashboard/.next/BUILD_ID — the dashboard was not built."
  missing=1
fi

if [[ "$missing" -ne 0 ]]; then
  echo
  echo "Units are installed but NOT enabled. Finish the install, then re-run:"
  echo
  cat <<EOF
  # Python (use python3.13/3.12/3.11/3.10; AL2023's default python3 is 3.9)
  cd $APP_DIR
  sudo dnf install -y python3.11 python3.11-pip || true
  rm -rf .venv
  python3.11 -m venv .venv            # or: python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -r requirements.txt
  PLAYWRIGHT_BROWSERS_PATH=$APP_DIR/.cache/ms-playwright .venv/bin/playwright install chromium
EOF
  if [[ "$WORKER_ONLY" != "1" ]]; then
    cat <<EOF

  # Node 22.14+ (not Node 20 — better-sqlite3 13 segfaults on Node 20)
  sudo dnf remove -y nodejs 2>/dev/null || true
  curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash -
  sudo dnf install -y nodejs
  node -v && npm -v

  # Dashboard
  cd $APP_DIR/dashboard
  npm ci || npm install
  npm run build
EOF
  fi
  cat <<EOF

  # Then
  sudo env WORKER_ONLY=$WORKER_ONLY bash $APP_DIR/deploy/ec2/install-services.sh
EOF
  exit 1
fi

systemctl enable --now applyforme-worker
systemctl restart applyforme-worker

if [[ "$WORKER_ONLY" != "1" ]]; then
  systemctl enable --now applyforme-web
  systemctl restart applyforme-web
fi

echo
systemctl --no-pager --full status applyforme-worker || true
if [[ "$WORKER_ONLY" != "1" ]]; then
  systemctl --no-pager --full status applyforme-web || true
fi

echo
echo -n "Worker health: "
if curl -fsS --max-time 5 http://127.0.0.1:8787/health; then
  echo
else
  echo "not ready yet"
  echo "Check: sudo journalctl -u applyforme-worker -n 80 --no-pager"
fi
