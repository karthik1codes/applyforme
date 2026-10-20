#!/bin/bash
# EC2 user-data for Amazon Linux (ec2-user). Also works if ubuntu exists.
#   aws ec2 run-instances --user-data file://deploy/ec2/user-data.sh …
set -euo pipefail
exec > /var/log/applyforme-userdata.log 2>&1

REPO_URL="${APPLYFORME_REPO_URL:-https://github.com/YOUR_USER/applyforme.git}"
REPO_BRANCH="${APPLYFORME_REPO_BRANCH:-main}"
APP_DIR=/opt/applyforme

# Amazon Linux → ec2-user; Ubuntu → ubuntu
if id -u ec2-user >/dev/null 2>&1; then
  APP_USER=ec2-user
elif id -u ubuntu >/dev/null 2>&1; then
  APP_USER=ubuntu
else
  APP_USER=ec2-user
  useradd -m -s /bin/bash "$APP_USER" || true
fi

sleep 5

if command -v dnf >/dev/null; then
  dnf install -y git curl ca-certificates
elif command -v yum >/dev/null; then
  yum install -y git curl ca-certificates
else
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y git curl ca-certificates
fi

mkdir -p "$APP_DIR"
chown "$APP_USER:$APP_USER" "$APP_DIR"

if [[ ! -d "$APP_DIR/.git" ]]; then
  sudo -u "$APP_USER" git clone --branch "$REPO_BRANCH" "$REPO_URL" "$APP_DIR"
else
  cd "$APP_DIR"
  sudo -u "$APP_USER" git fetch origin
  sudo -u "$APP_USER" git checkout "$REPO_BRANCH"
  sudo -u "$APP_USER" git pull --ff-only
fi

cd "$APP_DIR"
if [[ ! -f .env ]]; then
  sudo -u "$APP_USER" cp .env.example .env
fi

export APPLYFORME_USER="$APP_USER"
bash deploy/ec2/setup.sh

echo "user-data complete $(date -Is) user=$APP_USER" >> /var/log/applyforme-userdata.log
