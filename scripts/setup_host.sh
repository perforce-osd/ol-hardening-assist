#!/usr/bin/env bash
# One-time (idempotent) host setup for /hardening and /hardening-pr-review.
# Run this once per machine, before the first /hardening or
# /hardening-pr-review invocation, to install/verify everything the
# underlying Packer build needs: QEMU/KVM, HashiCorp Packer + its qemu
# plugin, oscap/scap-security-guide, ansible-playbook, and Python3+PyYAML —
# then confirms KVM acceleration is actually usable (device present,
# read/write, and the CPU exposes vmx/svm), since that can't be fixed by
# installing a package if the hypervisor isn't exposing nested
# virtualization to this VM.
#
# Safe to re-run: every step no-ops if already satisfied.
#
# Does NOT stage per-OS base images (e.g. /tmp/images/<os>-x86_64.qcow2)
# — that's a per-run input documented in the pipeline repo's own build
# docs, not a one-time host prerequisite.
#
# Usage: scripts/setup_host.sh

set -euo pipefail

FAIL=0

note() { echo "==> $*"; }
ok()   { echo "    OK: $*"; }
fail() { echo "    FAIL: $*" >&2; FAIL=1; }

if ! command -v dnf >/dev/null 2>&1; then
  echo "ERROR: this script only supports dnf-based hosts (RHEL/Rocky/Alma)." >&2
  echo "On another distro, install the equivalents by hand: qemu-kvm, packer," >&2
  echo "the packer qemu plugin, oscap/scap-security-guide, ansible-playbook," >&2
  echo "python3 + PyYAML — see README.md's Requirements section." >&2
  exit 1
fi

note "Checking qemu-kvm"
if rpm -q qemu-kvm >/dev/null 2>&1; then
  ok "qemu-kvm already installed"
else
  note "Installing qemu-kvm (sudo)"
  sudo dnf install -y qemu-kvm
fi

note "Checking /dev/kvm and nested-virtualization support"
if [[ -e /dev/kvm ]]; then
  ok "/dev/kvm present"
  if [[ -r /dev/kvm && -w /dev/kvm ]]; then
    ok "current user ($(whoami)) can read/write /dev/kvm"
  else
    fail "/dev/kvm exists but isn't read/write for $(whoami) — add this user to the 'kvm' group (sudo usermod -aG kvm $(whoami)) then re-login"
  fi
else
  fail "/dev/kvm not present after installing qemu-kvm"
fi
if grep -Eq 'vmx|svm' /proc/cpuinfo; then
  ok "CPU exposes vmx/svm (nested virtualization is available)"
else
  fail "no vmx/svm flag in /proc/cpuinfo — this VM's hypervisor isn't exposing nested virtualization to it. The pipeline's Packer build (accelerator = \"kvm\") will fail until nested virt is enabled in the underlying hypervisor's (e.g. VMware) settings for this VM. No package install can fix this — it needs to be changed outside this machine."
fi

note "Checking packer"
if command -v packer >/dev/null 2>&1; then
  ok "packer already installed ($(packer version | head -1))"
else
  note "Adding HashiCorp repo and installing packer (sudo)"
  sudo dnf install -y dnf-plugins-core
  sudo dnf config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
  sudo dnf install -y packer
fi

note "Checking packer's qemu plugin"
if packer plugins installed 2>/dev/null | grep -q packer-plugin-qemu; then
  ok "packer-plugin-qemu already installed"
else
  note "Installing packer-plugin-qemu"
  packer plugins install github.com/hashicorp/qemu
fi

note "Checking oscap / scap-security-guide"
if command -v oscap >/dev/null 2>&1; then
  ok "oscap present"
else
  note "Installing scap-security-guide (sudo)"
  sudo dnf install -y scap-security-guide
fi

note "Checking ansible-playbook"
if command -v ansible-playbook >/dev/null 2>&1; then
  ok "ansible-playbook present"
else
  note "Installing ansible-core (sudo)"
  sudo dnf install -y ansible-core
fi

note "Checking python3 + PyYAML"
if python3 -c "import yaml" >/dev/null 2>&1; then
  ok "python3 + PyYAML present"
else
  note "Installing python3-pyyaml (sudo)"
  sudo dnf install -y python3-pyyaml
fi

echo
if [[ "$FAIL" -eq 0 ]]; then
  echo "==> Host setup complete: all prerequisites satisfied."
else
  echo "==> Host setup finished with unresolved issues above — resolve those before running /hardening." >&2
  exit 1
fi
