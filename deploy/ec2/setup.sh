#!/usr/bin/env bash
# Bootstrap / update applyforme on Amazon Linux (ec2-user) or Ubuntu.
#   sudo bash deploy/ec2/setup.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/applyforme}"
# Set WORKER_ONLY=1 to run only the Python worker (no Next.js dashboard, no Node).
WORKER_ONLY="${WORKER_ONLY:-0}"

trap 'echo "setup.sh failed at line $LINENO — see the error above. If the systemd units are missing, run: sudo bash $APP_DIR/deploy/ec2/install-services.sh" >&2' ERR

# Prefer ec2-user (Amazon Linux); fall back to ubuntu / SUDO_USER
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
  echo "Run with sudo"; exit 1
fi

if [[ ! -d "$APP_DIR" ]]; then
  echo "Missing $APP_DIR — clone the repo there first (see deploy/ec2/PUSH.md)"; exit 1
fi

is_amazon=0
if [[ -f /etc/os-release ]] && grep -qiE 'amazon|amzn' /etc/os-release; then
  is_amazon=1
fi

pkg_install() {
  if [[ "$is_amazon" -eq 1 ]]; then
    if command -v dnf >/dev/null; then
      dnf install -y "$@"
    else
      yum install -y "$@"
    fi
  else
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y "$@"
  fi
}

echo "=== applyforme setup (user=$USER_NAME, amazon=$is_amazon) ==="

if [[ "$is_amazon" -eq 1 ]]; then
  # Amazon Linux 2 / 2023
  pkg_install git curl openssl nginx python3 python3-pip
  # venv module
  pkg_install python3-devel gcc || true
else
  pkg_install git curl openssl nginx python3 python3-venv python3-pip
fi

# The app needs Python >= 3.10. AL2023's default python3 is 3.9, so prefer a
# versioned interpreter and install 3.11 when none is new enough.
python_ok() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1
}
PYTHON3=""
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null && python_ok "$(command -v "$cand")"; then
    PYTHON3="$(command -v "$cand")"
    break
  fi
done
if [[ -z "$PYTHON3" ]]; then
  echo "No Python >= 3.10 found; installing python3.11"
  if [[ "$is_amazon" -eq 1 ]]; then
    pkg_install python3.11 python3.11-pip || pkg_install python3.11
  else
    pkg_install python3.11 python3.11-venv python3.11-dev
  fi
  PYTHON3="$(command -v python3.11)"
fi
"$PYTHON3" -m ensurepip --upgrade >/dev/null 2>&1 || true
echo "Using $PYTHON3 ($("$PYTHON3" -V 2>&1))"

# Node 22.14+ + dashboard (not needed for WORKER_ONLY).
# better-sqlite3 13 uses Node-API 10; Node 20/22 < 22.14 segfaults on first DB open.
node_ok() {
  command -v node >/dev/null 2>&1 || return 1
  local v major minor
  v="$(node -v 2>/dev/null | sed 's/^v//')"
  major="${v%%.*}"
  minor="${v#*.}"; minor="${minor%%.*}"
  [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ ]] || return 1
  (( major > 22 || (major == 22 && minor >= 14) ))
}

if [[ "$WORKER_ONLY" != "1" ]] && ! node_ok; then
  if [[ "$is_amazon" -eq 1 ]]; then
    curl -fsSL https://rpm.nodesource.com/setup_22.x | bash -
    pkg_install nodejs
  else
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    pkg_install nodejs
  fi
fi
if [[ "$WORKER_ONLY" != "1" ]] && ! node_ok; then
  echo "ERROR: Node.js 22.14+ is required (found $(node -v 2>/dev/null || echo none))." >&2
  echo "Node 20 causes better-sqlite3 13 to segfault on the first database open." >&2
  exit 1
fi

# npm path for systemd (only used by the web unit)
NPM_BIN="$(command -v npm || true)"

cd "$APP_DIR"
chown -R "$USER_NAME:$USER_NAME" "$APP_DIR"

# Install the units before the long Python/Node build so a later failure still
# leaves them visible in `systemctl status` (inactive) instead of "not found".
install -m 644 "$APP_DIR/deploy/ec2/applyforme-worker.service" /etc/systemd/system/
sed -i "s/^User=.*/User=$USER_NAME/" /etc/systemd/system/applyforme-worker.service
sed -i "s|/opt/applyforme|$APP_DIR|g" /etc/systemd/system/applyforme-worker.service

if [[ "$WORKER_ONLY" == "1" ]]; then
  # Remove the dashboard unit if a previous run installed it.
  systemctl disable --now applyforme-web 2>/dev/null || true
  rm -f /etc/systemd/system/applyforme-web.service
else
  install -m 644 "$APP_DIR/deploy/ec2/applyforme-web.service" /etc/systemd/system/
  sed -i "s/^User=.*/User=$USER_NAME/" /etc/systemd/system/applyforme-web.service
  sed -i "s|/opt/applyforme|$APP_DIR|g" /etc/systemd/system/applyforme-web.service
  sed -i "s|/usr/bin/npm|$NPM_BIN|g" /etc/systemd/system/applyforme-web.service
fi
systemctl daemon-reload

if [[ -x .venv/bin/python ]] && ! .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
  echo "Existing .venv uses an old Python — recreating it"
  rm -rf .venv
fi
if ! sudo -u "$USER_NAME" "$PYTHON3" -m venv .venv; then
  echo "venv creation failed — installing pip/venv support for $PYTHON3"
  if [[ "$is_amazon" -eq 1 ]]; then
    pkg_install python3.11-pip || true
  else
    pkg_install python3.11-venv || true
  fi
  sudo -u "$USER_NAME" "$PYTHON3" -m venv .venv
fi
sudo -u "$USER_NAME" .venv/bin/pip install -U pip
sudo -u "$USER_NAME" .venv/bin/pip install -r requirements.txt
sudo -u "$USER_NAME" .venv/bin/playwright install-deps chromium || true
sudo -u "$USER_NAME" mkdir -p .cache/ms-playwright
sudo -u "$USER_NAME" env PLAYWRIGHT_BROWSERS_PATH="$APP_DIR/.cache/ms-playwright" \
  .venv/bin/playwright install chromium

# Playwright's install-deps only knows Debian/Ubuntu. On AL2023 install the
# Chromium runtime libraries one by one so one renamed package can't block all.
if [[ "$is_amazon" -eq 1 ]]; then
  for p in nss nspr atk at-spi2-atk at-spi2-core cups-libs libdrm \
           libXcomposite libXdamage libXrandr mesa-libgbm pango alsa-lib \
           libXScrnSaver libXcursor libXext libXi libXfixes libXrender \
           libXtst libxkbcommon cairo dbus-libs glib2 fontconfig liberation-fonts; do
    pkg_install "$p" >/dev/null 2>&1 || true
  done
fi

if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chown "$USER_NAME:$USER_NAME" "$APP_DIR/.env"
fi

SECRET=$(openssl rand -hex 32)
AUTH=$(openssl rand -hex 32)
ensure_env() {
  local key="$1" val="$2"
  if grep -qE "^#?${key}=" "$APP_DIR/.env" 2>/dev/null; then
    sed -i "s|^#\\?${key}=.*|${key}=${val}|" "$APP_DIR/.env"
  else
    echo "${key}=${val}" >> "$APP_DIR/.env"
  fi
}
grep -q '^PIPELINE_WEBHOOK_SECRET=.\+' "$APP_DIR/.env" 2>/dev/null || ensure_env PIPELINE_WEBHOOK_SECRET "$SECRET"
grep -q '^AUTH_SECRET=.\+' "$APP_DIR/.env" 2>/dev/null || ensure_env AUTH_SECRET "$AUTH"
ensure_env PIPELINE_WORKER_URL "http://127.0.0.1:8787"
ensure_env PIPELINE_HOST "127.0.0.1"
ensure_env PIPELINE_PORT "8787"
grep -q '^SCHEDULE_RUN=' "$APP_DIR/.env" || ensure_env SCHEDULE_RUN "0 */4 * * *"
grep -q '^SCHEDULE_INBOX=' "$APP_DIR/.env" || ensure_env SCHEDULE_INBOX "30 */6 * * *"
grep -q '^SCHEDULE_INTERNSHIPS=' "$APP_DIR/.env" || ensure_env SCHEDULE_INTERNSHIPS "15 */6 * * *"
grep -q '^JOB_RETENTION_DAYS=' "$APP_DIR/.env" || ensure_env JOB_RETENTION_DAYS "10"
grep -q '^PYTHONUTF8=' "$APP_DIR/.env" || ensure_env PYTHONUTF8 "1"
sed -i 's/^AUTH_DISABLED=1/# AUTH_DISABLED=1/' "$APP_DIR/.env" || true

if [[ "$WORKER_ONLY" != "1" ]]; then
  cd "$APP_DIR/dashboard"
  sudo -u "$USER_NAME" "$NPM_BIN" ci || sudo -u "$USER_NAME" "$NPM_BIN" install
  sudo -u "$USER_NAME" "$NPM_BIN" run build
fi

systemctl enable --now applyforme-worker
systemctl restart applyforme-worker

if [[ "$WORKER_ONLY" == "1" ]]; then
  # Worker-only: make sure no dashboard unit or nginx site remains.
  rm -f /etc/nginx/conf.d/applyforme.conf /etc/nginx/sites-enabled/applyforme
  systemctl reload nginx 2>/dev/null || true
else
  systemctl enable --now applyforme-web
  systemctl restart applyforme-web

  # nginx — Amazon Linux uses conf.d; Ubuntu uses sites-available
  if [[ -f "$APP_DIR/deploy/ec2/nginx.conf" ]]; then
    PUB_IP=$(curl -fsS --max-time 2 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)
    TMP=$(mktemp)
    if [[ -n "$PUB_IP" ]]; then
      sed "s/apply.example.com/_/" "$APP_DIR/deploy/ec2/nginx.conf" > "$TMP"
    else
      cp "$APP_DIR/deploy/ec2/nginx.conf" "$TMP"
    fi
    if [[ -d /etc/nginx/sites-available ]]; then
      cp "$TMP" /etc/nginx/sites-available/applyforme
      ln -sf /etc/nginx/sites-available/applyforme /etc/nginx/sites-enabled/applyforme
      rm -f /etc/nginx/sites-enabled/default
    else
      # Amazon Linux / RHEL style
      mkdir -p /etc/nginx/conf.d
      # Drop default server if present so our config wins
      [[ -f /etc/nginx/conf.d/default.conf ]] && mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf.bak || true
      cp "$TMP" /etc/nginx/conf.d/applyforme.conf
    fi
    rm -f "$TMP"
    nginx -t && systemctl enable --now nginx && systemctl reload nginx
  fi
fi

# Firewall: prefer firewalld on Amazon Linux; ufw on Ubuntu. Security group is primary.
if command -v firewall-cmd >/dev/null; then
  firewall-cmd --permanent --add-service=ssh || true
  firewall-cmd --permanent --add-service=http || true
  firewall-cmd --permanent --add-service=https || true
  firewall-cmd --reload || true
elif command -v ufw >/dev/null; then
  ufw allow OpenSSH || true
  ufw allow 80/tcp || true
  ufw allow 443/tcp || true
  ufw --force enable || true
fi

echo ""
echo "=== applyforme running on this EC2 instance ==="
echo "OS user:  $USER_NAME"
echo "Worker:   systemctl status applyforme-worker"
if [[ "$WORKER_ONLY" == "1" ]]; then
  echo "Mode:     worker-only (dashboard is not installed)"
  echo "Health:   curl -s http://127.0.0.1:8787/health"
  echo ""
  echo "Edit secrets:  sudo nano $APP_DIR/.env"
  echo "Then:          sudo systemctl restart applyforme-worker"
else
  echo "Web:      systemctl status applyforme-web"
  echo "Health:   curl -s http://127.0.0.1:8787/health"
  echo ""
  echo "Edit secrets:  sudo nano $APP_DIR/.env"
  echo "Then:          sudo systemctl restart applyforme-worker applyforme-web"
fi
echo "SSH as:        ssh -i KEY.pem ec2-user@PUBLIC_IP"
echo "Security group: 22 / 80 / 443 — do NOT open 8787."
