#!/usr/bin/env python3
"""PreToolUse(Bash) guard for hardening-assist.

Deterministically enforces SKILL.md's hard rule: never `git commit` or
`git push` inside the dedicated pipeline checkout (`hardening-pipeline-main`
by default, see HARDENING_PIPELINE_DIR) -- full stop, no exceptions. That
checkout exists purely so /hardening has a stable, isolated copy of `main`
to build from; the only writes it should ever see are
`scripts/sync_pipeline_repo.sh`'s fetch/reset/clean.

Command text is split on `;`, `&`, `|`, and newlines into segments (a
best-effort approximation of shell command boundaries, not a full parser)
before any check runs, so context from an unrelated chained command can't
leak into the evaluation of a different one on the same line.

Output contract: print a PreToolUse JSON decision and exit 0.
"""
import sys
import re
import json

# Literal marker identifying the dedicated pipeline checkout. Update this if
# HARDENING_PIPELINE_DIR's default folder name ever changes (see SKILL.md).
PIPELINE_DIR_MARKERS = ("hardening-pipeline-main",)

GIT_WRITE_RE = re.compile(r"\bgit\b[^\n;&|]*?\b(commit|push)\b")
SEGMENT_SPLIT_RE = re.compile(r"[;&|\n]+")


def deny(reason):
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "Blocked by hardening-assist pipeline-repo guard: " + reason +
                ". The dedicated pipeline checkout (hardening-pipeline-main) "
                "is automation-only -- /hardening only ever reads from it and "
                "syncs it via scripts/sync_pipeline_repo.sh. It is never "
                "committed to or pushed from, no exceptions. To change "
                "pipeline code, use a separate feature-branch checkout of "
                "OSD-Linux-hardened-pipeline instead."
            ),
        }
    }
    print(json.dumps(out))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # not parseable -> do not block

    cmd = (data.get("tool_input") or {}).get("command", "") or ""

    segments = SEGMENT_SPLIT_RE.split(cmd)
    for seg in segments:
        if not GIT_WRITE_RE.search(seg):
            continue
        if any(marker in seg for marker in PIPELINE_DIR_MARKERS):
            deny("git commit/push targeting the pipeline checkout")

    sys.exit(0)


if __name__ == "__main__":
    main()
