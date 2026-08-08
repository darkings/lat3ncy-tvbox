#!/usr/bin/env bash
# A17/A19/A20: idempotent SSH deployment with recoverable backup
set -euo pipefail

DEPLOY_HOST="jie"
DEPLOY_PATH="/opt/ponyo-source-manager"
BACKUP_ROOT="/opt/ponyo-source-manager-backups"
SSH_OPTS=(-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o ServerAliveInterval=60)

echo "Creating pre-deploy backup..."
ssh.exe "${SSH_OPTS[@]}" "$DEPLOY_HOST" << 'EOF'
set -euo pipefail
DEPLOY_PATH="/opt/ponyo-source-manager"
BACKUP_ROOT="/opt/ponyo-source-manager-backups"
if [ -d "$DEPLOY_PATH" ]; then
  backup_id=$(date -u +%Y%m%dT%H%M%SZ)
  backup_dir="$BACKUP_ROOT/$backup_id"
  mkdir -p "$backup_dir"
  rsync -a --delete --exclude='.git/' --exclude='.venv/' --exclude='data/' \
    --exclude='logs/' --exclude='reports/' --exclude='subscription/' \
    "$DEPLOY_PATH/" "$backup_dir/"
  crontab -l > "$backup_dir/crontab.before" 2>/dev/null || :
  ln -sfn "$backup_id" "$BACKUP_ROOT/current"
fi
EOF

echo "Deploying Ponyo Source Manager..."
rsync -avz --delete \
  -e "ssh.exe -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o ServerAliveInterval=60" \
  --exclude='.git' --exclude='.venv' --exclude='__pycache__' --exclude='*.db' \
  --exclude='data/' --exclude='cache/' --exclude='logs/' --exclude='reports/' \
  --exclude='subscription/' --exclude='.tmp/' --exclude='review.md' \
  ./ "$DEPLOY_HOST:$DEPLOY_PATH/"

ssh.exe "${SSH_OPTS[@]}" "$DEPLOY_HOST" << 'EOF'
set -euo pipefail
DEPLOY_PATH="/opt/ponyo-source-manager"
cd "$DEPLOY_PATH"
chmod +x scripts/provision-drpy-node.sh
scripts/provision-drpy-node.sh
if [ ! -d ".venv" ]; then python3 -m venv .venv; fi
.venv/bin/pip install -U pip
.venv/bin/pip install -e .
.venv/bin/python -m ponyo_source_manager.core.initdb

existing_cron=$(mktemp)
new_cron=$(mktemp)
trap 'rm -f "$existing_cron" "$new_cron"' EXIT
crontab -l > "$existing_cron" 2>/dev/null || :
sed '/# BEGIN PONYO MANAGED/,/# END PONYO MANAGED/d' "$existing_cron" \
  | grep -v 'ponyo_source_manager\.scheduler' \
  | grep -v 'scheduler\.py' > "$new_cron" || :
.venv/bin/python -m ponyo_source_manager.scheduler --phase crontab >> "$new_cron"
crontab "$new_cron"

if [ -f "docker-compose.yml" ]; then
  docker compose build --quiet
  docker compose run --rm --user root --entrypoint sh scheduler -c \
    "mkdir -p /app/data /app/reports /app/logs /app/subscription && chown -R ponyo:ponyo /app/data /app/reports /app/logs /app/subscription && su ponyo -c 'touch /app/data/.write-test && rm /app/data/.write-test'"
  docker compose up -d
fi
echo "Deployment successful."
EOF
