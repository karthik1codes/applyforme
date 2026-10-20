# EC2 deployment runbook

## Recommendation: run the dashboard on EC2, tunnel port 3000

Run **both** `applyforme-worker` and `applyforme-web` on the instance. Open the
dashboard from your laptop through an SSH tunnel:

```text
laptop:3000  ──SSH tunnel──▶  EC2 127.0.0.1:3000
```

Do **not** use the “worker on EC2 + dashboard on laptop + SQLite sync” setup as
your primary deployment.

Why:

- The worker and dashboard share one SQLite database on EC2. Running the
  dashboard locally creates a second database, so jobs and status changes
  diverge.
- The worker’s scheduled discovery/apply runs continue when your laptop sleeps
  or loses network.
- There is nothing to sync, merge, or reconcile.
- The dashboard stays on `127.0.0.1`; only SSH port 22 is exposed.
- Backup and restore are one database, one instance.

Use sync only for a read-only snapshot or backup. It is not a safe control
plane: status changes made in a local dashboard do not reach the EC2 worker.

---

## Mode A — recommended

### 0. Before you start

On your laptop:

```bash
cd /path/to/applyforme
git status --short
git diff --stat
```

Push the code you intend to deploy. The EC2 clone only sees what is on the
remote branch.

Security group:

- Inbound: **22 only** for tunnel-only access.
- Do **not** open `3000` or `8787`.
- Add `80`/`443` only later if you put nginx + TLS + authentication in front.

Instance size: use at least **2 GB RAM** (`t3.small` minimum). `t3.medium`
(4 GB) is safer for `npm run build`.

Node.js: use **22.14+**. Node 20 is not supported: `better-sqlite3@13` uses
Node-API 10 and segfaults on the first database open under Node 20.

### 1. Bootstrap the instance

```bash
ssh -i ~/.ssh/applyforme.pem ec2-user@YOUR_EC2_IP

sudo dnf install -y git
sudo mkdir -p /opt/applyforme
sudo chown ec2-user:ec2-user /opt/applyforme

git clone https://github.com/YOUR_USER/applyforme.git /opt/applyforme
cd /opt/applyforme
cp .env.example .env
nano .env
```

Set these values in `/opt/applyforme/.env`:

```dotenv
OPENAI_API_KEY=sk-...
APP_URL=http://localhost:3000

PIPELINE_WEBHOOK_SECRET=
AUTH_SECRET=

PIPELINE_WORKER_URL=http://127.0.0.1:8787
PIPELINE_HOST=127.0.0.1
PIPELINE_PORT=8787

SCHEDULE_RUN=0 */4 * * *
SCHEDULE_INTERNSHIPS=15 */6 * * *
SCHEDULE_INBOX=30 */6 * * *
JOB_RETENTION_DAYS=10
```

If `OPENAI_API_KEY` starts with `sk-or-v1-`, it is an OpenRouter key, not an
OpenAI key. Add both lines or resume parsing and every LLM step will fail with
`401 invalid_api_key`:

```dotenv
OPENAI_BASE_URL=https://openrouter.ai/api/v1
APPLYFORME_MODEL=openai/gpt-4o-mini
```

Generate the two secrets on the instance if they are empty or commented out:

```bash
cd /opt/applyforme

if ! grep -qE '^PIPELINE_WEBHOOK_SECRET=.+' .env; then
  sed -i "s|^#\?PIPELINE_WEBHOOK_SECRET=.*|PIPELINE_WEBHOOK_SECRET=$(openssl rand -hex 32)|" .env
  grep -qE '^PIPELINE_WEBHOOK_SECRET=.+' .env || \
    echo "PIPELINE_WEBHOOK_SECRET=$(openssl rand -hex 32)" >> .env
fi

if ! grep -qE '^AUTH_SECRET=.+' .env; then
  sed -i "s|^#\?AUTH_SECRET=.*|AUTH_SECRET=$(openssl rand -hex 32)|" .env
  grep -qE '^AUTH_SECRET=.+' .env || \
    echo "AUTH_SECRET=$(openssl rand -hex 32)" >> .env
fi
```

If you are not configuring Google sign-in tomorrow, leave
`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` empty. Auth is skipped when no
provider is configured. Keep port 3000 private in that mode.

### Reusing your existing local `.env`

It is fine to copy your local `.env` to EC2, but use `scp` rather than a chat
paste: the file contains API keys. Back up the old one first.

On your laptop:

```bash
scp -i ~/.ssh/applyforme.pem /path/to/applyforme/.env \
  ec2-user@YOUR_EC2_IP:/tmp/applyforme.env
```

On EC2:

```bash
sudo cp /opt/applyforme/.env \
  /opt/applyforme/.env.bak.$(date +%F-%H%M) 2>/dev/null || true

sudo install -m 600 -o ec2-user -g ec2-user \
  /tmp/applyforme.env /opt/applyforme/.env

# Windows CRLF line endings can leave a trailing \r in API keys.
sudo sed -i 's/\r$//' /opt/applyforme/.env

rm -f /tmp/applyforme.env
```

Now apply the EC2-specific differences:

```bash
cd /opt/applyforme

# EC2 is headless. Headed/slow-motion browser settings are for a desktop.
grep -q '^APPLYFORME_BROWSER_HEADED=' .env || \
  echo 'APPLYFORME_BROWSER_HEADED=0' >> .env
sed -i 's/^APPLYFORME_BROWSER_HEADED=.*/APPLYFORME_BROWSER_HEADED=0/' .env

grep -q '^APPLYFORME_BROWSER_SLOW_MO=' .env || \
  echo 'APPLYFORME_BROWSER_SLOW_MO=0' >> .env
sed -i 's/^APPLYFORME_BROWSER_SLOW_MO=.*/APPLYFORME_BROWSER_SLOW_MO=0/' .env

# Use the tunnel URL, not an old public/Cloudflare URL.
grep -q '^DODO_PAYMENTS_RETURN_URL=' .env || \
  echo 'DODO_PAYMENTS_RETURN_URL=http://localhost:3000/billing?checkout=success' >> .env
sed -i 's|^DODO_PAYMENTS_RETURN_URL=.*|DODO_PAYMENTS_RETURN_URL=http://localhost:3000/billing?checkout=success|' .env

# Values setup.sh normally adds.
grep -q '^PIPELINE_HOST=' .env || echo 'PIPELINE_HOST=127.0.0.1' >> .env
grep -q '^PIPELINE_PORT=' .env || echo 'PIPELINE_PORT=8787' >> .env
grep -q '^SCHEDULE_INTERNSHIPS=' .env || echo 'SCHEDULE_INTERNSHIPS=15 */6 * * *' >> .env
grep -q '^JOB_RETENTION_DAYS=' .env || echo 'JOB_RETENTION_DAYS=10' >> .env

chmod 600 .env
```

### LinkedIn Easy Apply on a headless worker

LinkedIn postings are opened on LinkedIn rather than the employer ATS, so the
agent can use Easy Apply. A headless EC2 worker cannot show LinkedIn's sign-in
window, though. If `FIRECRAWL_API_KEY` is set, the worker automatically uses
Firecrawl for LinkedIn listings and keeps its live view open while you sign in;
the agent continues as soon as the session is ready.

1. Keep `APPLYFORME_BROWSER_HEADED=0`.
2. Set `FIRECRAWL_API_KEY=fc-...` and, optionally,
   `APPLYFORME_LINKEDIN_ENGINE=firecrawl` (`auto` already selects Firecrawl for
   LinkedIn on a headless worker).
3. Click **Prepare application**, then open the **Firecrawl live view** shown on
   the job page and finish LinkedIn sign-in/2FA there.
4. The Firecrawl profile (`FIRECRAWL_BROWSER_PROFILE`, default `applyforme`)
   keeps the session for later LinkedIn applications.

How the Firecrawl session works, and why it used to fail:

* A Firecrawl browser profile has **exactly one writer**. While a session is
  alive on a profile, any other session on that profile is rejected with
  `HTTP 409 Browser operation conflicts with the current session or profile state`.
* The agent now opens **one** standalone session (`POST /v2/interact`), records
  it in SQLite, and always releases it in a `finally` block. A session left
  behind by a crashed run is reclaimed automatically on the next run, so one
  crash can no longer wedge the profile for every later application.
* The whole form flow runs over the returned CDP websocket using the same
  deterministic Playwright code as the local browser. No AI browser agent is in
  the loop (2 credits/minute instead of 7).
* Only sessions that this installation created are ever reclaimed, and only
  when they are idle **and** their job no longer holds a live apply lock.
  Concurrent applications are never disturbed.

Use `APPLYFORME_LINKEDIN_ENGINE=playwright` only when the worker has a display,
or when a signed-in persistent `data/browser` profile has been copied to it.
Without a Firecrawl key or a session, the worker returns a clear "LinkedIn
sign-in required" note instead of waiting on a login window it cannot show.

`profile.yaml` is gitignored and is **not** in the repo. Without it, the
dashboard's onboarding/profile pages throw `ENOENT`. `setup.sh` creates it from
`profile.example.yaml` when missing. To create it manually:

```bash
cd /opt/applyforme
cp profile.example.yaml profile.yaml
chown ec2-user:ec2-user profile.yaml
```

The onboarding wizard fills in the real values.

If `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` are present, add this exact
redirect URI in Google:

```text
http://localhost:3000/api/auth/callback/google
```

and set:

```dotenv
AUTH_URL=http://localhost:3000
NEXTAUTH_URL=http://localhost:3000
```

If you are not configuring Google tomorrow, after `setup.sh` finishes run:

```bash
cd /opt/applyforme
sed -i 's/^AUTH_DISABLED=.*/AUTH_DISABLED=1/' .env
grep -q '^AUTH_DISABLED=' .env || echo 'AUTH_DISABLED=1' >> .env
sudo systemctl restart applyforme-web
```

Only do that while port 3000 is reachable solely through the SSH tunnel.


`APP_URL=http://localhost:3000` is correct for the SSH-tunnel setup because the
browser reaches the app at `http://localhost:3000` on your laptop.

### 2. Install and start

```bash
cd /opt/applyforme
sudo bash deploy/ec2/setup.sh
```

Verify:

```bash
sudo systemctl status applyforme-worker applyforme-web --no-pager
curl -s http://127.0.0.1:8787/health
curl -sI http://127.0.0.1:3000 | head -n 1
```

Both services should be `active (running)`, and the health endpoint should
return JSON.

### 3. Open the dashboard from your laptop

```bash
ssh -i ~/.ssh/applyforme.pem -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -L 3000:127.0.0.1:3000 \
  ec2-user@YOUR_EC2_IP
```

Leave that terminal open and browse to:

```text
http://localhost:3000
```

The worker remains on `127.0.0.1:8787`; the dashboard talks to it locally on
EC2.

### 4. Daily operation

Logs:

```bash
sudo journalctl -u applyforme-worker -f
sudo journalctl -u applyforme-web -f
```

Restart after editing `.env`:

```bash
sudo systemctl restart applyforme-worker applyforme-web
```

Update code:

```bash
cd /opt/applyforme
git pull
sudo bash deploy/ec2/setup.sh
```

Backup the database while the app is running:

```bash
cd /opt/applyforme
.venv/bin/python - <<'PY'
import sqlite3

src = sqlite3.connect("data/applyforme.db")
dst = sqlite3.connect("/tmp/applyforme-backup.db")
src.backup(dst)
dst.close()
src.close()
PY

ls -lh /tmp/applyforme-backup.db
```

---

## Mode B — worker only, dashboard on your laptop

This works, but it is **not recommended** because the databases are separate.
Use it only if you accept that the EC2 worker is the system of record and the
local dashboard is a read-only view.

### 1. Deploy only the worker

```bash
cd /opt/applyforme
sudo env WORKER_ONLY=1 bash deploy/ec2/setup.sh
```

If the web service was already installed:

```bash
sudo systemctl disable --now applyforme-web 2>/dev/null || true
sudo rm -f /etc/systemd/system/applyforme-web.service
sudo systemctl daemon-reload
sudo systemctl enable --now applyforme-worker
```

Remove the old nginx proxy:

```bash
sudo rm -f /etc/nginx/conf.d/applyforme.conf /etc/nginx/sites-enabled/applyforme
sudo nginx -t && sudo systemctl reload nginx
```

Node and the dashboard build are not needed for the worker. Optional cleanup:

```bash
sudo dnf remove -y nodejs
sudo rm -rf /opt/applyforme/dashboard/node_modules /opt/applyforme/dashboard/.next
```

### 2. Connect the local dashboard to the EC2 worker

On your laptop:

```bash
ssh -i ~/.ssh/applyforme.pem -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -L 8787:127.0.0.1:8787 \
  ec2-user@YOUR_EC2_IP
```

In your **local** `.env`:

```dotenv
PIPELINE_WORKER_URL=http://127.0.0.1:8787
PIPELINE_WEBHOOK_SECRET=<same value as /opt/applyforme/.env on EC2>
```

Read the secret from EC2:

```bash
ssh -i ~/.ssh/applyforme.pem ec2-user@YOUR_EC2_IP \
  "grep '^PIPELINE_WEBHOOK_SECRET=' /opt/applyforme/.env"
```

### 3. Sync the EC2 database for viewing

The local dashboard reads its own `data/applyforme.db`. The EC2 worker writes
`/opt/applyforme/data/applyforme.db`. These are not shared.

Create a consistent snapshot on EC2:

```bash
cd /opt/applyforme
.venv/bin/python - <<'PY'
import sqlite3

src = sqlite3.connect("data/applyforme.db")
dst = sqlite3.connect("/tmp/applyforme.db")
src.backup(dst)
dst.close()
src.close()
PY
```

Copy it to your laptop (stop the local dashboard first):

```bash
scp -i ~/.ssh/applyforme.pem \
  ec2-user@YOUR_EC2_IP:/tmp/applyforme.db \
  ./data/applyforme.db
```

This is a one-way snapshot. Changes made in the local dashboard are written to
the local database and will not reach the EC2 worker. If you need to change job
status, approve applications, or edit settings, use Mode A instead.

---

## Troubleshooting

Unit missing:

```bash
cd /opt/applyforme
sudo bash deploy/ec2/install-services.sh
```

Dashboard build missing:

```bash
cd /opt/applyforme/dashboard
npm ci || npm install
npm run build
```

Check listeners:

```bash
sudo ss -ltnp | grep -E '3000|8787'
```

Check logs:

```bash
sudo journalctl -u applyforme-worker -n 120 --no-pager
sudo journalctl -u applyforme-web -n 120 --no-pager
```

Never expose `8787` in the security group. Access it only from the instance or
through an SSH tunnel.
