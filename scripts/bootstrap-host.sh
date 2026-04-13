#!/usr/bin/env bash
# bootstrap-host.sh — idempotent reconcile of ATLAS host-level artifacts.
#
# Guarantees that the things a chunk cannot recreate from source alone
# (systemd unit files, env files, nginx site) match what the repo ships.
# Runs on every post-chunk pass, so drift self-heals instead of surfacing
# as a 502 the next time someone opens the dashboard.
#
# Reconciles:
#   - /etc/systemd/system/atlas-frontend.service  <- backend/systemd/atlas-frontend.service
#   - /etc/atlas/frontend.env                     <- default if missing
#   - /etc/nginx/sites-available/forge            <- infra/nginx/forge.conf
#   - sites-enabled symlink + nginx reload when the config actually changed
#   - systemctl enable atlas-frontend.service (install only; runtime start
#     is done by post-chunk.sh after the build step)
#
# Idempotent: safe to run repeatedly. Exits non-zero only if a reconcile
# step fails outright (bad nginx syntax, systemd failure) — never on
# "nothing to do".

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/ubuntu/atlas}"
log() { echo "[bootstrap-host] $*"; }
err() { echo "[bootstrap-host] ERROR: $*" >&2; }

# --- systemd: atlas-frontend.service -----------------------------------
SRC_UNIT="$REPO_ROOT/backend/systemd/atlas-frontend.service"
DST_UNIT="/etc/systemd/system/atlas-frontend.service"
if [ ! -f "$SRC_UNIT" ]; then
  err "repo unit file missing: $SRC_UNIT"
  exit 1
fi
if ! sudo cmp -s "$SRC_UNIT" "$DST_UNIT" 2>/dev/null; then
  log "installing atlas-frontend.service"
  sudo cp "$SRC_UNIT" "$DST_UNIT"
  sudo systemctl daemon-reload
  sudo systemctl enable atlas-frontend.service >/dev/null 2>&1 || true
else
  log "atlas-frontend.service up-to-date"
fi

# --- env: /etc/atlas/frontend.env --------------------------------------
ENV_DIR="/etc/atlas"
ENV_FILE="$ENV_DIR/frontend.env"
if [ ! -f "$ENV_FILE" ]; then
  log "seeding $ENV_FILE"
  sudo mkdir -p "$ENV_DIR"
  echo 'NEXT_PUBLIC_API_URL=http://127.0.0.1:8010' | sudo tee "$ENV_FILE" >/dev/null
  sudo chmod 0644 "$ENV_FILE"
else
  log "$ENV_FILE present"
fi

# --- nginx: sites-available/forge --------------------------------------
SRC_NGINX="$REPO_ROOT/infra/nginx/forge.conf"
DST_NGINX="/etc/nginx/sites-available/forge"
LINK_NGINX="/etc/nginx/sites-enabled/forge"
nginx_changed=0
if [ ! -f "$SRC_NGINX" ]; then
  err "repo nginx config missing: $SRC_NGINX"
  exit 1
fi
if ! sudo cmp -s "$SRC_NGINX" "$DST_NGINX" 2>/dev/null; then
  log "installing nginx forge site"
  sudo cp "$SRC_NGINX" "$DST_NGINX"
  nginx_changed=1
fi
if [ ! -L "$LINK_NGINX" ]; then
  log "enabling nginx forge site"
  sudo ln -sf "$DST_NGINX" "$LINK_NGINX"
  nginx_changed=1
fi
if [ "$nginx_changed" = "1" ]; then
  if sudo nginx -t 2>&1 | tail -5; then
    sudo systemctl reload nginx
    log "nginx reloaded"
  else
    err "nginx -t failed — refusing to reload"
    exit 1
  fi
else
  log "nginx forge site up-to-date"
fi

log "reconcile complete"
