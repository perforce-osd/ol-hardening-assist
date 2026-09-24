#!/usr/bin/env python3
"""
Parse an OpenSCAP XCCDF HTML evaluation report and list every rule not in
PASS/NOTAPPLICABLE state, excluding any rule ID already present in an
exclusions.yaml file.

Usage:
    parse_report.py <report.html> [exclusions.yaml]

Output: JSON on stdout:
{
  "counts": {"pass": N, "fail": N, "notapplicable": N, ...},
  "failed": [
    {"rule_id": "...", "title": "...", "severity": "...", "cis": ["6.1.1"]},
    ...
  ],
  "excluded_skipped": ["rule_id", ...]   # failed rules omitted because excluded
}

Relies on the report's rule-overview table row structure:
  <tr data-tt-id="xccdf_org.ssgproject.content_rule_X"
      class="rule-overview-leaf rule-overview-leaf-<result> ..."
      data-references='{"cis": ["1.2.3"], ...}'>
    <td ...><a href="#rule-detail-..." ...>Title</a></td>
    <td class="rule-severity" ...>severity</td>
    <td class="rule-result rule-result-<result>">...</td>
  </tr>
"""
import sys
import re
import json

try:
    import yaml
except ImportError:
    yaml = None

ROW_RE = re.compile(
    r'<tr data-tt-id="(?P<id>xccdf_org\.ssgproject\.content_rule_[^"]+)"'
    r'[^>]*class="[^"]*rule-overview-leaf-(?P<result>fail|pass|notapplicable|'
    r'notchecked|error|unknown|informational|fixed)[^"]*"'
    r'[^>]*data-references=\'(?P<refs>\{.*?\})\'>'
    r'.*?<a href="#rule-detail-[^"]*"[^>]*>(?P<title>[^<]*)</a>',
    re.DOTALL,
)

NON_FAIL_STATES = {"pass", "notapplicable", "fixed", "informational"}


def load_exclusions(path):
    if not path or yaml is None:
        return set()
    try:
        with open(path) as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return set()
    return {e["rule_id"] for e in (data.get("exclusions") or []) if e.get("rule_id")}


def main():
    if len(sys.argv) < 2:
        print("usage: parse_report.py <report.html> [exclusions.yaml]", file=sys.stderr)
        sys.exit(1)

    report_path = sys.argv[1]
    exclusions_path = sys.argv[2] if len(sys.argv) > 2 else None
    excluded_ids = load_exclusions(exclusions_path)

    with open(report_path, encoding="utf-8", errors="replace") as fh:
        html = fh.read()

    counts = {}
    failed = []
    excluded_skipped = []

    for m in ROW_RE.finditer(html):
        result = m.group("result")
        counts[result] = counts.get(result, 0) + 1

        if result in NON_FAIL_STATES:
            continue

        rule_id = m.group("id")
        if rule_id in excluded_ids:
            excluded_skipped.append(rule_id)
            continue

        try:
            refs = json.loads(m.group("refs"))
        except json.JSONDecodeError:
            refs = {}

        failed.append({
            "rule_id": rule_id,
            "title": m.group("title").strip(),
            "result": result,
            "cis": refs.get("cis", []),
        })

    print(json.dumps({
        "counts": counts,
        "failed": failed,
        "excluded_skipped": excluded_skipped,
    }, indent=2))


if __name__ == "__main__":
    main()
