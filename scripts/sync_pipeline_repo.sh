#!/usr/bin/env bash
# Syncs the dedicated pipeline-repo checkout used by /hardening to the
# latest origin/main. This checkout is automation-only: /hardening only
# ever reads pipeline code from it to drive Packer builds. It is fetched
# and hard-reset here, never committed to or pushed from.
#
# On a fresh machine (no checkout yet at <pipeline_dir>), this also does
# the initial single-branch clone, so first-time setup on a new machine
# never has to ask where OSD-Linux-hardened-pipeline lives.
#
# Usage: sync_pipeline_repo.sh <pipeline_dir>

set -euo pipefail

PIPELINE_DIR="${1:?pipeline_dir required}"

# Default clone URL for OSD-Linux-hardened-pipeline. Override with
# $HARDENING_PIPELINE_REPO_URL if a machine needs a different remote
# (e.g. HTTPS instead of SSH, or a fork) — see SKILL.md Configuration.
PIPELINE_REPO_URL="${HARDENING_PIPELINE_REPO_URL:-git@github.com:perforce-osd/OSD-Linux-hardened-pipeline.git}"

if [[ ! -e "$PIPELINE_DIR" ]]; then
  echo "==> No checkout at $PIPELINE_DIR yet; cloning $PIPELINE_REPO_URL (branch main)"
  git clone --single-branch --branch main "$PIPELINE_REPO_URL" "$PIPELINE_DIR"
fi

if [[ ! -d "$PIPELINE_DIR/.git" ]]; then
  echo "ERROR: $PIPELINE_DIR is not a git checkout" >&2
  exit 1
fi

CURRENT_BRANCH="$(git -C "$PIPELINE_DIR" rev-parse --abbrev-ref HEAD)"
if [[ "$CURRENT_BRANCH" != "main" ]]; then
  echo "ERROR: $PIPELINE_DIR is on branch '$CURRENT_BRANCH', expected 'main'." >&2
  echo "This checkout is dedicated to main for /hardening automation; refusing to touch it." >&2
  exit 1
fi

if [[ -n "$(git -C "$PIPELINE_DIR" status --porcelain)" ]]; then
  echo "ERROR: $PIPELINE_DIR has uncommitted changes (likely remediation edits" >&2
  echo "left over from a previous run's Step 3, per SKILL.md — they were never" >&2
  echo "committed on purpose, for review). Refusing to reset/clean and destroy them." >&2
  echo "Copy out or commit-elsewhere whatever's needed from that diff first, e.g.:" >&2
  echo "  git -C '$PIPELINE_DIR' diff > /tmp/pending_remediation.diff" >&2
  echo "then re-run this script." >&2
  exit 1
fi

echo "==> Fetching origin/main into $PIPELINE_DIR"
git -C "$PIPELINE_DIR" fetch origin main

echo "==> Resetting to origin/main (discards any local changes/leftover build artifacts)"
git -C "$PIPELINE_DIR" reset --hard origin/main
git -C "$PIPELINE_DIR" clean -fdx

echo "==> $PIPELINE_DIR now at $(git -C "$PIPELINE_DIR" rev-parse --short HEAD) (origin/main)"
