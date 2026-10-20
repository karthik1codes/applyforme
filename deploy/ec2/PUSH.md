# Deploy & run applyforme on AWS EC2 (Amazon Linux · `ec2-user`)

For the recommended topology and a copy-paste runbook for deployment day, see
[`deploy/ec2/DEPLOY.md`](DEPLOY.md). Short version: run both the worker and the
dashboard on EC2, and reach port 3000 through an SSH tunnel.

SSH user is **`ec2-user`** (not `ubuntu`). By default systemd runs `applyforme-worker` + `applyforme-web` as that user. Port **8787** stays on localhost. Set `WORKER_ONLY=1` if the dashboard runs on your laptop.

## First time on an existing Amazon Linux instance

```bash
# From your laptop
ssh -i ~/.ssh/your-key.pem ec2-user@YOUR_EC2_IP

# On the instance
sudo mkdir -p /opt/applyforme
sudo chown ec2-user:ec2-user /opt/applyforme
git clone https://github.com/YOUR_USER/applyforme.git /opt/applyforme
cd /opt/applyforme

cp .env.example .env
nano .env
# set at least:
#   OPENAI_API_KEY=…
#   CRUSTDATA_API_KEY=…   (optional but recommended)
#   APP_URL=http://YOUR_EC2_IP
#   PIPELINE_WEBHOOK_SECRET=…  (or let setup.sh generate one)

sudo bash deploy/ec2/setup.sh
```

`setup.sh` detects Amazon Linux, installs deps with `dnf`/`yum`, sets `User=ec2-user` in systemd, and configures nginx under `/etc/nginx/conf.d/`.

## `Unit applyforme-worker.service could not be found`

`setup.sh` runs with `set -e`: it stops at the first failure, and the units are installed before the Python/Node build so they stay visible as **inactive** if a later step fails. If they are still missing, the run stopped before Node was installed.

```bash
cd /opt/applyforme

# What is actually missing?
ls -l .venv/bin/python dashboard/.next/BUILD_ID 2>&1
command -v python3.11 node npm

# 1) Install the units unconditionally (safe to re-run)
sudo bash deploy/ec2/install-services.sh
```

`install-services.sh` prints the exact remaining commands when the venv or dashboard build is missing. Typical completion:

```bash
cd /opt/applyforme

# Python 3.11+ (AL2023's default python3 is 3.9 — too old)
sudo dnf install -y python3.11 python3.11-pip
rm -rf .venv
python3.11 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
PLAYWRIGHT_BROWSERS_PATH=/opt/applyforme/.cache/ms-playwright \
  .venv/bin/playwright install chromium

# Node 22.14+ (not Node 20 — better-sqlite3 13 segfaults on Node 20)
sudo dnf remove -y nodejs 2>/dev/null || true
curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash -
sudo dnf install -y nodejs
node -v && npm -v

# Dashboard
cd dashboard
npm ci || npm install
npm run build
cd ..

# 2) Re-run: installs, enables, starts, and checks health
sudo bash deploy/ec2/install-services.sh

sudo journalctl -u applyforme-worker -n 80 --no-pager
```

To capture the original failure next time:

```bash
sudo bash deploy/ec2/setup.sh 2>&1 | tee /tmp/applyforme-setup.log
tail -50 /tmp/applyforme-setup.log
```

## Worker-only (dashboard runs on your laptop)

If only the Python worker should run on EC2:

```bash
cd /opt/applyforme

# Stop and remove the dashboard service
sudo systemctl disable --now applyforme-web
sudo rm -f /etc/systemd/system/applyforme-web.service
sudo systemctl daemon-reload

# Keep the worker enabled/running
sudo systemctl enable --now applyforme-worker
curl -s http://127.0.0.1:8787/health
```

Use worker-only mode on future setup/update runs so the dashboard is not reinstalled:

```bash
cd /opt/applyforme
sudo env WORKER_ONLY=1 bash deploy/ec2/setup.sh
# or, if the units already exist:
sudo env WORKER_ONLY=1 bash deploy/ec2/install-services.sh
```

The worker binds `127.0.0.1:8787`, so from your laptop open an SSH tunnel:

```bash
ssh -i ~/.ssh/your-key.pem -N -L 8787:127.0.0.1:8787 ec2-user@YOUR_EC2_IP
```

Then set your **local** dashboard `.env`:

```dotenv
PIPELINE_WORKER_URL=http://127.0.0.1:8787
PIPELINE_WEBHOOK_SECRET=<same value as /opt/applyforme/.env on EC2>
```

> **Database caveat:** the local dashboard reads `data/applyforme.db`
> (or `APPLYFORME_DB`). The EC2 worker writes `/opt/applyforme/data/applyforme.db`.
> Those are separate SQLite files — sync the DB from EC2, or the local dashboard
> won't show the jobs the EC2 worker fetched.

## After setup — secrets & restart

```bash
ssh -i ~/.ssh/your-key.pem ec2-user@YOUR_EC2_IP

sudo nano /opt/applyforme/.env
sudo systemctl restart applyforme-worker applyforme-web
sudo systemctl status applyforme-worker applyforme-web --no-pager

curl -s http://127.0.0.1:8787/health
```

## Everyday updates

```bash
ssh -i ~/.ssh/your-key.pem ec2-user@YOUR_EC2_IP
cd /opt/applyforme
git pull
sudo bash deploy/ec2/setup.sh
```

Faster (code-only, deps unchanged):

```bash
cd /opt/applyforme/dashboard && npm ci && npm run build
sudo systemctl restart applyforme-worker applyforme-web
```

## Trigger pipelines

```bash
ssh -i ~/.ssh/your-key.pem ec2-user@YOUR_EC2_IP
set -a; source /opt/applyforme/.env; set +a

# Jobs lane
curl -X POST http://127.0.0.1:3000/api/pipeline/webhook \
  -H "Authorization: Bearer $PIPELINE_WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"stage":"run","limit":40}'

# Internships lane (parallel)
curl -X POST http://127.0.0.1:3000/api/pipeline/webhook \
  -H "Authorization: Bearer $PIPELINE_WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"stage":"internships","limit":40}'
```

Or open `http://YOUR_EC2_IP` → **Settings** / **Internships**.

## Fresh listings & retention

Every fetch records `last_seen_at` per listing, then automatically:

- removes cross-board duplicates (same role, including company-name variants)
- drops untouched `new` / `matched` / `skipped` rows older than `JOB_RETENTION_DAYS` (default **10**)
- leaves `applied`, `ready` (tailored), `manual`, and in-progress jobs untouched

```bash
ssh -i ~/.ssh/your-key.pem ec2-user@YOUR_EC2_IP
cd /opt/applyforme

# Preview what would be removed
.venv/bin/python -m applyforme cleanup --dry-run

# Apply now (also runs after every discover / internships run)
.venv/bin/python -m applyforme cleanup

# Change the window: 7 days, or 0 to disable
sudo sed -i 's/^JOB_RETENTION_DAYS=.*/JOB_RETENTION_DAYS=7/' .env
sudo systemctl restart applyforme-worker
```

Trigger the same maintenance through the worker:

```bash
set -a; source /opt/applyforme/.env; set +a
curl -X POST http://127.0.0.1:8787/hooks/cleanup \
  -H "Authorization: Bearer $PIPELINE_WEBHOOK_SECRET"
```

## Logs

```bash
sudo journalctl -u applyforme-worker -f
sudo journalctl -u applyforme-web -f
sudo tail -f /var/log/applyforme-userdata.log   # if launched with user-data
```

## Security group

| Port | Open? |
|------|--------|
| 22 | your IP only |
| 80 / 443 | yes (public or LB) |
| **8787** | **no** — localhost only |

## Optional: launch a new Amazon Linux 2023 box

```bash
export AWS_REGION=ap-south-1
export KEY_NAME=your-keypair
export APPLYFORME_REPO_URL=https://github.com/YOUR_USER/applyforme.git
export ALLOCATE_EIP=1          # optional: stable public IP
bash deploy/ec2/launch-ec2.sh
# SSH as: ssh -i ~/.ssh/your-keypair.pem ec2-user@PUBLIC_IP
```

## TLS (certbot on Amazon Linux)

```bash
sudo dnf install -y certbot python3-certbot-nginx   # or: sudo yum install …
sudo certbot --nginx -d your.domain
# set APP_URL=https://your.domain in .env, then:
sudo systemctl restart applyforme-worker applyforme-web
```
