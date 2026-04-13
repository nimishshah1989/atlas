#!/usr/bin/env bash
# smoke-probe.sh — post-deploy slice probe for ATLAS forge orchestrator.
#
# Called by scripts/post-chunk.sh after deploy, before context sync. Reads
# scripts/smoke-endpoints.txt and hits every URL with curl. A non-2xx on any
# HARD endpoint exits 1 — the runner then marks the chunk BLOCKED so you see
# the regression instead of shipping "green gate, dead product" (see
# docs/specs/version-demo-gate.md for the bigger picture).
#
# Lines starting with "?" are OPTIONAL: non-2xx is tolerated UNLESS the code
# is 5xx (a 500 on a listed endpoint is always a regression, but a 404 is
# fine because maybe that chunk hasn't built it yet).
#
# Usage:
#   scripts/smoke-probe.sh                       # defaults to smoke-endpoints.txt
#   scripts/smoke-probe.sh path/to/list.txt      # custom list
#   SMOKE_TIMEOUT=10 scripts/smoke-probe.sh      # per-endpoint timeout seconds
#
# Environment:
#   SMOKE_LIST       — path override (default: scripts/smoke-endpoints.txt)
#   SMOKE_TIMEOUT    — per-request timeout seconds (default: 5)
#   SMOKE_QUIET      — set to 1 to only print on failure

set -u
set -o pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LIST="${1:-${SMOKE_LIST:-$REPO_ROOT/scripts/smoke-endpoints.txt}}"
TIMEOUT="${SMOKE_TIMEOUT:-5}"
QUIET="${SMOKE_QUIET:-0}"

log() { [ "$QUIET" = "1" ] || echo "[smoke] $*"; }
err() { echo "[smoke] $*" >&2; }

if [ ! -f "$LIST" ]; then
  err "no smoke list at $LIST — nothing to probe (treating as pass)"
  exit 0
fi

if ! command -v curl >/dev/null 2>&1; then
  err "curl not available — cannot run smoke probe"
  exit 2
fi

hard_fail=0
soft_fail=0
passed=0
total=0

while IFS= read -r raw || [ -n "$raw" ]; do
  # trim leading/trailing whitespace, skip blanks and comments
  line="${raw#"${raw%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [ -z "$line" ] && continue
  case "$line" in '#'*) continue ;; esac

  optional=0
  if [ "${line:0:1}" = "?" ]; then
    optional=1
    line="${line:1}"
  fi

  total=$((total + 1))
  status=$(curl -sS -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "$line" 2>/dev/null || echo "000")

  if [ "$status" -ge 200 ] && [ "$status" -lt 300 ] 2>/dev/null; then
    log "PASS $status  $line"
    passed=$((passed + 1))
    continue
  fi

  if [ "$optional" = "1" ]; then
    # Optional: tolerate 000/3xx/4xx, fail only on 5xx (real regression).
    if [ "$status" -ge 500 ] 2>/dev/null; then
      err "OPTIONAL-FAIL $status  $line   (5xx on optional = regression)"
      hard_fail=$((hard_fail + 1))
    else
      log "SKIP $status  $line   (optional)"
      soft_fail=$((soft_fail + 1))
    fi
  else
    err "FAIL $status  $line"
    hard_fail=$((hard_fail + 1))
  fi
done <"$LIST"

log "summary: total=$total passed=$passed hard_fail=$hard_fail soft_skip=$soft_fail"

if [ "$hard_fail" -gt 0 ]; then
  err "smoke probe failed: $hard_fail hard fail(s) — chunk will be BLOCKED"
  exit 1
fi
exit 0
