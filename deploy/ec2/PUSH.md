# Deploy & run applyforme on AWS EC2 (Amazon Linux · `ec2-user`)

SSH user is **`ec2-user`** (not `ubuntu`). systemd runs `applyforme-worker` + `applyforme-web` as that user. Port **8787** stays on localhost.

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
