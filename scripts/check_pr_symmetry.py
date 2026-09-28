#!/usr/bin/env python3
"""
Mechanical gap-checker for one OSD-Linux-hardened-pipeline PR diff.

Takes a unified diff (as produced by `gh pr diff <n>`) and reports, purely
from pattern-matching the added (`+`) lines — no judgment calls:

  - files changed, grouped by OS folder
  - remediation tasks/blocks added to remediation-playbook.yml (Ansible
    `- name:` entries) or remediation_script.sh (`# benchmark X.Y.Z`
    comments), with their CIS number references
  - QA test blocks added to QA.yaml (`- name: X.Y.Z ...` entries)
  - rule idrefs newly tailored out (`selected="false"` added) in any
    harden/*-customization-*.xml
  - any changed file that looks like a raw vendored SSG datastream
    (ssg-*-ds.xml, not the customization/tailoring file) — a Hard Rule
    violation candidate (see hardening-assist CLAUDE.md)
  - symmetry mismatches: a CIS number added to remediation with no matching
    QA test and vice versa (per .claude/skills/hardening/SKILL.md Step
    3.2b), and a CIS number that is both newly tailored-out AND has a QA
    test added (Step 5 says excluded rules need no QA test)

This script only reports facts; it does not fetch the diff itself (see the
hardening-pr-review skill for that) and it makes no judgment about whether
a flagged item is actually wrong — e.g. a profile/tailoring-loop mismatch
in perform_hardening.sh, or a PR-description-vs-code drift, both require
reading actual script/prose content and are intentionally left to the
skill's own instructed steps, not this script.

Usage:
    check_pr_symmetry.py <diff_file>
    gh pr diff <n> --repo <owner>/<repo> | check_pr_symmetry.py -

Output: JSON on stdout.
"""
import sys
import re
import json
from collections import defaultdict

FILE_HEADER_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)")
HUNK_HEADER_RE = re.compile(r"^@@ .* @@")
CIS_NUM_RE = re.compile(r"\b(\d+(?:\.\d+){1,4})\b")
ANSIBLE_NAME_RE = re.compile(r'^\+\s*-\s*name:\s*(.+?)\s*$')
BENCHMARK_COMMENT_RE = re.compile(r'^\+\s*#\s*benchmark\s+(\d+(?:\.\d+){1,4})', re.IGNORECASE)
TAILORING_SELECT_RE = re.compile(
    r'^\+\s*<xccdf:select\s+idref="([^"]+)"\s+selected="false"'
)


def parse_diff(text):
    """Split a unified diff into per-file (path, added_lines) records."""
    files = []
    current_path = None
    current_lines = []

    for line in text.splitlines():
        m = FILE_HEADER_RE.match(line)
        if m:
            if current_path is not None:
                files.append((current_path, current_lines))
            current_path = m.group(2)
            current_lines = []
            continue
        if current_path is not None and line.startswith("+") and not line.startswith("+++"):
            current_lines.append(line)

    if current_path is not None:
        files.append((current_path, current_lines))

    return files


def os_folder_of(path):
    return path.split("/", 1)[0] if "/" in path else path


def cis_numbers_in(text):
    return set(CIS_NUM_RE.findall(text))


def is_remediation_file(path):
    return path.endswith("remediation-playbook.yml") or path.endswith("remediation_script.sh")


def is_qa_file(path):
    return path.endswith("QA.yaml")


def is_tailoring_file(path):
    return "customization" in path and path.endswith(".xml")


def is_vendored_datastream(path):
    fname = path.rsplit("/", 1)[-1]
    return fname.startswith("ssg-") and fname.endswith("-ds.xml") and "customization" not in fname


def extract_remediation_entries(added_lines):
    entries = []
    for line in added_lines:
        m = ANSIBLE_NAME_RE.match(line)
        if m:
            name = m.group(1)
            nums = cis_numbers_in(name)
            if nums:
                entries.append({"name": name, "cis_numbers": sorted(nums)})
            continue
        m = BENCHMARK_COMMENT_RE.match(line)
        if m:
            entries.append({"name": line.lstrip("+ ").strip(), "cis_numbers": [m.group(1)]})
    return entries


def extract_qa_entries(added_lines):
    entries = []
    for line in added_lines:
        m = ANSIBLE_NAME_RE.match(line)
        if m:
            name = m.group(1)
            nums = cis_numbers_in(name)
            if nums:
                entries.append({"name": name, "cis_numbers": sorted(nums)})
    return entries


def extract_tailoring_selects(added_lines):
    return [m.group(1) for line in added_lines if (m := TAILORING_SELECT_RE.match(line))]


def main():
    if len(sys.argv) != 2:
        print("usage: check_pr_symmetry.py <diff_file|->", file=sys.stderr)
        sys.exit(1)

    src = sys.argv[1]
    text = sys.stdin.read() if src == "-" else open(src, encoding="utf-8", errors="replace").read()

    files = parse_diff(text)

    by_os_files = defaultdict(list)
    remediation_by_os = defaultdict(list)
    qa_by_os = defaultdict(list)
    tailoring_excludes_by_os = defaultdict(list)
    vendored_datastream_touched = []

    for path, added_lines in files:
        os_name = os_folder_of(path)
        by_os_files[os_name].append(path)

        if is_vendored_datastream(path):
            vendored_datastream_touched.append(path)
        elif is_remediation_file(path):
            remediation_by_os[os_name].extend(extract_remediation_entries(added_lines))
        elif is_qa_file(path):
            qa_by_os[os_name].extend(extract_qa_entries(added_lines))
        elif is_tailoring_file(path):
            tailoring_excludes_by_os[os_name].extend(extract_tailoring_selects(added_lines))

    symmetry_gaps = {}
    for os_name in set(remediation_by_os) | set(qa_by_os):
        remediation_nums = {n for e in remediation_by_os.get(os_name, []) for n in e["cis_numbers"]}
        qa_nums = {n for e in qa_by_os.get(os_name, []) for n in e["cis_numbers"]}

        missing_qa = sorted(remediation_nums - qa_nums)
        extra_qa = sorted(qa_nums - remediation_nums)
        if missing_qa or extra_qa:
            symmetry_gaps[os_name] = {
                "remediation_without_qa_test": missing_qa,
                "qa_test_without_remediation": extra_qa,
            }

    result = {
        "files_changed_by_os": dict(by_os_files),
        "remediation_entries_added": {k: v for k, v in remediation_by_os.items() if v},
        "qa_entries_added": {k: v for k, v in qa_by_os.items() if v},
        "tailoring_excludes_added": {k: v for k, v in tailoring_excludes_by_os.items() if v},
        "vendored_datastream_touched": vendored_datastream_touched,
        "symmetry_gaps": symmetry_gaps,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
