#!/usr/bin/env python3
"""
Best-effort remediation-source lookup for one failed CIS rule ID.

Checks, in order:
  1. Does this OS folder's own remediation-playbook.yml (Ansible, RPM-family)
     or remediation_script.sh (bash, Debian/Ubuntu) already contain a task
     tagged/named for this rule? (existing hand-written custom remediation)
  2. Does the SCAP Security Guide datastream for this OS ship a canned
     <fix> for this rule, checkable via `oscap xccdf generate fix --rule-id`?
     Only checkable if a matching datastream is reachable on this host —
     for Rocky/Alma the real datastream only exists inside the build VM, so
     this check may come back "not available locally".

This script only reports facts; it does not write any remediation itself.
Follow REMEDIATION_PERSONA.md in the pipeline repo to decide what to do
with these facts (add an Ansible task / bash block, matching existing style).

Usage:
    lookup_remediation.py <pipeline_dir> <os_name> <rule_id>

Output: JSON on stdout.
"""
import sys
import os
import re
import json

# Map an OS folder name prefix to a locally-installed SSG datastream path,
# for OSes that don't vendor their own datastream in harden/.
LOCAL_DATASTREAM_CANDIDATES = {
    "rocky8": "/usr/share/xml/scap/ssg/content/ssg-rl8-ds.xml",
    "rocky9": "/usr/share/xml/scap/ssg/content/ssg-rl9-ds.xml",
    "alma8": "/usr/share/xml/scap/ssg/content/ssg-almalinux8-ds.xml",
    "alma9": "/usr/share/xml/scap/ssg/content/ssg-almalinux9-ds.xml",
}


def find_existing_coverage(os_dir, rule_id):
    short_name = rule_id.rsplit("content_rule_", 1)[-1]

    for fname in ("remediation-playbook.yml", "remediation_script.sh"):
        fpath = os.path.join(os_dir, fname)
        if not os.path.isfile(fpath):
            continue
        with open(fpath, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()

        matches = []
        pattern = re.compile(re.escape(short_name), re.IGNORECASE)
        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                matches.append({"line": i, "text": line.strip()})

        if matches:
            return {"found": True, "file": fpath, "matches": matches[:10]}

    return {"found": False, "file": None, "matches": []}


def find_vendored_datastream(os_dir):
    harden_dir = os.path.join(os_dir, "harden")
    if not os.path.isdir(harden_dir):
        return None
    for fname in os.listdir(harden_dir):
        if fname.startswith("ssg-") and fname.endswith("-ds.xml") and "customization" not in fname:
            return os.path.join(harden_dir, fname)
    return None


def find_tailoring_file(os_dir):
    harden_dir = os.path.join(os_dir, "harden")
    if not os.path.isdir(harden_dir):
        return None
    for fname in os.listdir(harden_dir):
        if "customization" in fname and fname.endswith(".xml"):
            return os.path.join(harden_dir, fname)
    return None


RULE_TAG_RE_TMPL = r'<xccdf-1\.2:Rule\b[^>]*\bid="{}"[^>]*>'


def check_datastream_fix(os_name, os_dir, rule_id):
    """Directly inspect the SSG datastream XML for an embedded <fix> for
    this rule. oscap's CLI has no `--rule-id` filter for `generate fix`
    (it only operates on a prior eval's results.xml), so the reliable way
    to pre-check auto-fix coverage for a single rule is to look at the
    raw datastream content instead of shelling out to oscap.
    """
    ds_path = find_vendored_datastream(os_dir)
    source = "vendored"
    if not ds_path:
        for prefix, path in LOCAL_DATASTREAM_CANDIDATES.items():
            if os_name.startswith(prefix) and os.path.isfile(path):
                ds_path = path
                source = "local-host-package"
                break

    if not ds_path:
        return {
            "available": False,
            "path": None,
            "has_fix": None,
            "note": "No datastream reachable on this host for this OS; "
                    "SSG auto-fix coverage cannot be pre-checked outside the build VM.",
        }

    with open(ds_path, encoding="utf-8", errors="replace") as fh:
        content = fh.read()

    rule_open_re = re.compile(RULE_TAG_RE_TMPL.format(re.escape(rule_id)))
    m = rule_open_re.search(content)
    if not m:
        return {
            "available": True,
            "path": ds_path,
            "source": source,
            "has_fix": None,
            "note": "rule id not found in this datastream (check spelling / OS match)",
        }

    close_idx = content.find("</xccdf-1.2:Rule>", m.end())
    body = content[m.end():close_idx if close_idx != -1 else m.end() + 20000]

    fix_systems = sorted(set(re.findall(r'<xccdf-1\.2:fix\b[^>]*\bsystem="([^"]+)"', body)))
    has_ansible = any("ansible" in s for s in fix_systems)
    has_bash = any(s.endswith(":sh") for s in fix_systems)

    return {
        "available": True,
        "path": ds_path,
        "source": source,
        "has_fix": bool(fix_systems),
        "has_ansible_fix": has_ansible,
        "has_bash_fix": has_bash,
        "fix_systems": fix_systems,
        "note": None,
    }


def main():
    if len(sys.argv) != 4:
        print("usage: lookup_remediation.py <pipeline_dir> <os_name> <rule_id>", file=sys.stderr)
        sys.exit(1)

    pipeline_dir, os_name, rule_id = sys.argv[1], sys.argv[2], sys.argv[3]
    os_dir = os.path.join(pipeline_dir, os_name)
    if not os.path.isdir(os_dir):
        print(f"ERROR: OS folder not found: {os_dir}", file=sys.stderr)
        sys.exit(1)

    result = {
        "rule_id": rule_id,
        "existing_coverage": find_existing_coverage(os_dir, rule_id),
        "datastream_check": check_datastream_fix(os_name, os_dir, rule_id),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
