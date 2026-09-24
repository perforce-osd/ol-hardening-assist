#!/usr/bin/env bash
# Runs the existing OSD-Linux-hardened-pipeline Packer build for one OS folder
# and copies the resulting artifacts into a build-iteration directory.
#
# Usage: run_pipeline.sh <pipeline_dir> <os_name> <iteration_dir> [cis_version] [content_cache_dir]
#
# <pipeline_dir>       path to the OSD-Linux-hardened-pipeline checkout
# <os_name>            folder name inside <pipeline_dir>, e.g. rocky8.10
# <iteration_dir>      where to copy this build's artifacts (created if missing)
# <cis_version>        optional ComplianceAsCode/content release tag (e.g.
#                       0.1.81) to pin the SCAP datastream to, instead of
#                       whatever the OS folder relies on by default (distro
#                       package for Rocky/Alma, already-vendored file for
#                       Debian/Ubuntu). Omit to use the existing default.
# <content_cache_dir>  where fetch_content.sh caches downloads; defaults to
#                       <runs_dir>/_content_cache (runs_dir derived from
#                       iteration_dir, which is always <runs_dir>/<run>/iteration-N)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PIPELINE_DIR="${1:?pipeline_dir required}"
OS_NAME="${2:?os_name required}"
ITER_DIR="${3:?iteration_dir required}"
CIS_VERSION="${4:-}"
CONTENT_CACHE_DIR="${5:-$ITER_DIR/../../_content_cache}"

OS_DIR="$PIPELINE_DIR/$OS_NAME"

if [[ ! -d "$OS_DIR" ]]; then
  echo "ERROR: OS folder not found: $OS_DIR" >&2
  echo "Available OS folders:" >&2
  find "$PIPELINE_DIR" -maxdepth 1 -mindepth 1 -type d -printf '  %f\n' >&2
  exit 1
fi

if [[ ! -f "$OS_DIR/config.pkr.hcl" ]]; then
  echo "ERROR: no config.pkr.hcl in $OS_DIR" >&2
  exit 1
fi

mkdir -p "$ITER_DIR"

STAGED_DS=""
if [[ -n "$CIS_VERSION" ]]; then
  echo "==> Pinning SCAP content to ComplianceAsCode/content v$CIS_VERSION"
  FETCHED_DS="$("$SCRIPT_DIR/fetch_content.sh" "$CIS_VERSION" "$OS_NAME" "$CONTENT_CACHE_DIR")"
  STAGED_DS="$OS_DIR/harden/$(basename "$FETCHED_DS")"
  cp "$FETCHED_DS" "$STAGED_DS"
  echo "==> Staged $STAGED_DS for this build (untracked, removed after build)"
fi

cleanup_staged_ds() {
  if [[ -n "$STAGED_DS" && -f "$STAGED_DS" ]]; then
    rm -f "$STAGED_DS"
  fi
}
trap cleanup_staged_ds EXIT

echo "==> Building $OS_NAME via Packer ($OS_DIR/config.pkr.hcl)"
(
  cd "$OS_DIR"
  packer init config.pkr.hcl || true
  packer build -force config.pkr.hcl
)

echo "==> Collecting artifacts from $OS_DIR into $ITER_DIR"

mkdir -p "$ITER_DIR/harden-scan-results" "$ITER_DIR/output"

shopt -s nullglob

for f in "$OS_DIR"/harden-scan-results/*; do
  cp -v "$f" "$ITER_DIR/harden-scan-results/"
done

for f in "$OS_DIR"/harden-scan-results.zip "$OS_DIR"/remediation-scripts.zip; do
  [[ -f "$f" ]] && cp -v "$f" "$ITER_DIR/"
done

if [[ -f "$ITER_DIR/harden-scan-results.zip" ]]; then
  unzip -o -q "$ITER_DIR/harden-scan-results.zip" -d "$ITER_DIR/harden-scan-results"
fi

for f in "$OS_DIR"/output/*.qcow2 "$OS_DIR"/output-*/*.qcow2; do
  [[ -f "$f" ]] && cp -v "$f" "$ITER_DIR/output/"
done

shopt -u nullglob

HARDENED_REPORT=$(find "$ITER_DIR/harden-scan-results" -iname "*hardened*.html" ! -iname "*unhardened*" | head -1)
if [[ -z "$HARDENED_REPORT" ]]; then
  echo "ERROR: no hardened report found after build" >&2
  exit 1
fi

echo "==> Hardened report: $HARDENED_REPORT"
echo "$HARDENED_REPORT"
