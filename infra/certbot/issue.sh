#!/usr/bin/env bash
# Issue a Let's Encrypt certificate for the ATLAS forge dashboard.
#
# Usage:  sudo DOMAIN=atlas.jslwealth.in EMAIL=ops@jslwealth.in ./issue.sh
#
# Idempotent — certbot will skip renewal if the cert is fresh.
# Auto-renewal runs from /etc/cron.d/certbot (installed by certbot package).

set -euo pipefail

DOMAIN="${DOMAIN:-atlas.jslwealth.in}"
EMAIL="${EMAIL:-ops@jslwealth.in}"
WEBROOT="/var/www/certbot"

if [[ $EUID -ne 0 ]]; then
  echo "must run as root (sudo)" >&2
  exit 1
fi

if ! command -v certbot >/dev/null 2>&1; then
  echo "installing certbot…"
  apt-get update -qq
  apt-get install -y certbot python3-certbot-nginx
fi

mkdir -p "$WEBROOT"

certbot certonly \
  --webroot \
  --webroot-path "$WEBROOT" \
  --domain "$DOMAIN" \
  --email "$EMAIL" \
  --agree-tos \
  --non-interactive \
  --keep-until-expiring \
  --rsa-key-size 4096

echo "cert issued/renewed for $DOMAIN"
echo "reload nginx with: sudo systemctl reload nginx"

# Validate auto-renewal
systemctl list-timers certbot.timer || true
