#!/usr/bin/env bash
# Downloads (with local caching + sha512 verification) a specific
# ComplianceAsCode/content release and extracts the one datastream file
# needed for a given OS folder.
#
# Usage: fetch_content.sh <cis_version> <os_name> <cache_dir>
#
# <cis_version>  ComplianceAsCode/content release tag without the 'v'
#                prefix, e.g. 0.1.81 (see
#                https://github.com/ComplianceAsCode/content/releases)
# <os_name>      pipeline OS folder name, e.g. rocky8.10
# <cache_dir>    where to cache the downloaded tarball + extracted files
#                (shared across OSes/runs at the same cis_version)
#
# Prints the path to the extracted ds.xml on stdout. Writes nothing outside
# <cache_dir>.

set -euo pipefail

CIS_VERSION="${1:?cis_version required, e.g. 0.1.81}"
OS_NAME="${2:?os_name required}"
CACHE_DIR="${3:?cache_dir required}"

# Map a pipeline OS folder name to the upstream ComplianceAsCode product's
# datastream filename. Rocky/Alma 8.x share RHEL8 content upstream (their
# distro packages just rename ssg-rhel8-ds.xml to ssg-rl8-ds.xml /
# ssg-almalinux8-ds.xml); Rocky 9.x shares RHEL9; Alma 9.x has its own
# upstream product. Debian/Ubuntu already match 1:1.
case "$OS_NAME" in
  rocky8.9|rocky8.10|alma8.10)   UPSTREAM_DS="ssg-rhel8-ds.xml" ;;
  rocky9.5)                      UPSTREAM_DS="ssg-rhel9-ds.xml" ;;
  alma9.5)                       UPSTREAM_DS="ssg-almalinux9-ds.xml" ;;
  debian12)                      UPSTREAM_DS="ssg-debian12-ds.xml" ;;
  ubuntu22.04)                   UPSTREAM_DS="ssg-ubuntu2204-ds.xml" ;;
  ubuntu24.04)                   UPSTREAM_DS="ssg-ubuntu2404-ds.xml" ;;
  *)
    echo "ERROR: no known ComplianceAsCode product mapping for os_name=$OS_NAME" >&2
    exit 1
    ;;
esac

VERSION_DIR="$CACHE_DIR/$CIS_VERSION"
TARBALL="scap-security-guide-${CIS_VERSION}.tar.gz"
TARBALL_PATH="$VERSION_DIR/$TARBALL"
EXTRACTED_PATH="$VERSION_DIR/$UPSTREAM_DS"
BASE_URL="https://github.com/ComplianceAsCode/content/releases/download/v${CIS_VERSION}"

mkdir -p "$VERSION_DIR"

if [[ -f "$EXTRACTED_PATH" ]]; then
  echo "==> Using cached $EXTRACTED_PATH" >&2
  echo "$EXTRACTED_PATH"
  exit 0
fi

if [[ ! -f "$TARBALL_PATH" ]]; then
  echo "==> Downloading $TARBALL from ComplianceAsCode/content v$CIS_VERSION" >&2
  curl -sL --fail -o "$TARBALL_PATH" "$BASE_URL/$TARBALL"
  curl -sL --fail -o "$TARBALL_PATH.sha512" "$BASE_URL/$TARBALL.sha512"

  echo "==> Verifying sha512 checksum" >&2
  (cd "$VERSION_DIR" && sha512sum -c "$TARBALL.sha512") >&2
fi

echo "==> Extracting $UPSTREAM_DS from $TARBALL" >&2
tar -xzf "$TARBALL_PATH" -O "scap-security-guide-${CIS_VERSION}/${UPSTREAM_DS}" > "$EXTRACTED_PATH.tmp"
mv "$EXTRACTED_PATH.tmp" "$EXTRACTED_PATH"

echo "$EXTRACTED_PATH"
