#!/usr/bin/env bash
# A19: restore the latest pre-deploy code/Cron backup and previous release
set -euo pipefail

DEPLOY_HOST="jie"
SSH_OPTS=(-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o ServerAliveInterval=60)

echo "Rolling back Ponyo Source Manager..."
ssh.exe "${SSH_OPTS[@]}" "$DEPLOY_HOST" << 'EOF'
set -euo pipefail
DEPLOY_PATH="/opt/ponyo-source-manager"
BACKUP_ROOT="/opt/ponyo-source-manager-backups"
BACKUP_DIR=$(readlink -f "$BACKUP_ROOT/current" 2>/dev/null || true)
if [ -z "$BACKUP_DIR" ] || [ ! -d "$BACKUP_DIR" ]; then
  echo "No pre-deploy backup is available." >&2
  exit 1
fi

mkdir -p "$DEPLOY_PATH"
rsync -a --delete --exclude='.venv/' --exclude='data/' --exclude='logs/' \
  --exclude='reports/' --exclude='subscription/' --exclude='crontab.before' "$BACKUP_DIR/" "$DEPLOY_PATH/"
cd "$DEPLOY_PATH"
if [ ! -d ".venv" ]; then python3 -m venv .venv; fi
.venv/bin/pip install -e .

if [ -f "$BACKUP_DIR/crontab.before" ]; then
  crontab "$BACKUP_DIR/crontab.before"
else
  echo "Backup has no crontab.before; refusing a partial rollback." >&2
  exit 1
fi

if [ -d "subscription" ]; then
  cd subscription
  current_target=$(readlink current 2>/dev/null || true)
  previous_version=$(find . -mindepth 1 -maxdepth 1 -type d -name '20*' -printf '%f\n' \
    | sort -r | grep -Fvx "$current_target" | head -n 1 || true)
  if [ -n "$previous_version" ] && [ -d "$previous_version" ]; then
    temp_link=".current.rollback.$$"
    ln -s "$previous_version" "$temp_link"
    mv -Tf "$temp_link" current
    echo "Rolled subscription back to $previous_version"
  else
    echo "No previous subscription version found; code/Cron rollback continues."
  fi
  cd "$DEPLOY_PATH"
fi

if [ -f "docker-compose.yml" ]; then docker compose up -d --build --remove-orphans; fi
echo "Rollback successful from $BACKUP_DIR"
EOF
