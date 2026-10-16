# Push applyforme to EC2 and go live

Replace `YOUR_EC2_IP` (or use your domain) and the key path.

## 1. First time (new instance)

```bash
# On your laptop — copy the repo up (or clone from GitHub on the box)
ssh -i ~/.ssh/your-key.pem ubuntu@YOUR_EC2_IP

sudo mkdir -p /opt/applyforme
sudo chown ubuntu:ubuntu /opt/applyforme
git clone https://github.com/YOUR_USER/applyforme.git /opt/applyforme
cd /opt/applyforme

# Secrets
cp .env.example .env
nano .env   # OPENAI_API_KEY, PIPELINE_WEBHOOK_SECRET, APP_URL=https://your.domain, AUTH_*, Google OAuth…

sudo bash deploy/ec2/setup.sh
```

Point DNS A-record at the instance, then:

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your.domain
```

Open security group: **22** (your IP), **80**, **443**. Do **not** open **8787**.

## 2. Every update (push new code)

From your laptop:

```bash
git add -A
git commit -m "your message"
git push origin main
```

On EC2:

```bash
ssh -i ~/.ssh/your-key.pem ubuntu@YOUR_EC2_IP
cd /opt/applyforme
git pull origin main
sudo bash deploy/ec2/setup.sh
# or faster if deps unchanged:
#   cd dashboard && npm ci && npm run build
#   sudo systemctl restart applyforme-worker applyforme-web
```

## 3. Check it’s live

```bash
curl -s http://127.0.0.1:8787/health
curl -s https://your.domain/api/pipeline/webhook
sudo systemctl status applyforme-worker applyforme-web --no-pager
```

Trigger a search:

```bash
source /opt/applyforme/.env
curl -X POST https://your.domain/api/pipeline/webhook \
  -H "Authorization: Bearer $PIPELINE_WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"stage":"run","limit":40}'
```

Or open **Settings** in the dashboard → **Find new jobs now**.
