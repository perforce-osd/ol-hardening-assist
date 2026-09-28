# hardening-assist

This file is the always-loaded workspace context for Claude Code, the
equivalent of `ol-cve-assist`'s `CLAUDE.md` but for CIS hardening instead of
CVE backporting. Full step-by-step behavior lives in
`.claude/skills/hardening/SKILL.md` (read on demand when `/hardening` runs)
and `.claude/skills/hardening-pr-review/SKILL.md` (read on demand when
`/hardening-pr-review` runs) — this file is the map, not the manual.

## What this project is

A standalone Claude Code project: `cd` here and run Claude Code directly to
get `/hardening` and `/hardening-pr-review` available immediately, no other
setup needed. `/hardening` automates the CIS hardening loop for
`OSD-Linux-hardened-pipeline` — build the hardened image, scan it,
remediate every failing benchmark not already excluded, and repeat until
everything is PASSED or EXCLUDED. `/hardening-pr-review` reviews an
already-open PR from that loop for gaps and always confirms fixes with a
real build, rather than stopping at code review.

```
/hardening <OS_NAME> <CIS_VERSION>
/hardening-pr-review <pr_number_or_url> [os_name]
```

Example: `/hardening rocky8.10 0.1.81`,
`/hardening-pr-review 47`

## Hard rules

- **Never `git commit` or `git push` in the pipeline checkout
  (`hardening-pipeline-main`), full stop, no exceptions.** It exists solely
  so `/hardening` has a stable, isolated copy of `main` to build from. A
  `.claude/hooks/block-pipeline-write.py` PreToolUse hook denies any Bash
  command that runs `git commit`/`git push` naming that checkout, as a
  deterministic backstop — but don't rely on the hook catching everything
  it wasn't written to anticipate; treat the rule itself as absolute.
- Leave remediation edits (`remediation-playbook.yml`/`remediation_script.sh`
  and `QA.yaml` in the pipeline checkout) as an **uncommitted diff for
  review** — that's the intended, permanent state for those files, not a
  TODO to clean up.
- Never add to, weaken, or remove an entry in a per-OS `exclusions.yaml`
  without an explicit reason / explicit user ask (see SKILL.md Step 3 and
  Guardrails).
- Adding a rule to `exclusions.yaml` also means adding a matching
  `selected="false"` entry for it to the OS's own SCAP tailoring file
  (`harden/*-customization-perforce-CIS.xml`) — the two edits are one
  action, not two lists to keep in sync separately (see SKILL.md Step 5).
  Because an excluded rule is no longer scanned at all, it also needs no
  `QA.yaml` regression test (see SKILL.md Step 3, sub-step 2b) — there's
  nothing left to guard against regressing.
- Never hand-edit a vendored/installed SSG datastream XML outside the
  existing sanctioned OVAL-check `sed` patches in `perform_hardening.sh`.
  (The SCAP tailoring/customization file above is a separate overlay, not
  the vendored datastream itself, so editing it per the rule above is
  fine.)

## Architecture — three roles, one project directory

```
hardening-assist/                              <- this project (git repo, no remote)
  CLAUDE.md                                     <- this file
  .claude/skills/hardening/SKILL.md             <- the skill Claude follows
  .claude/hooks/block-pipeline-write.py         <- PreToolUse guard (see Hard rules)
  scripts/                                      <- sync/build/parse/lookup helpers
  exclusions.yaml                               <- template only, not the live list

  hardening-pipeline-main/                      <- dedicated pipeline checkout
                                                    (nested, gitignored — see .gitignore)
    - a single-branch `git clone` of OSD-Linux-hardened-pipeline's `main`
    - automation-only: /hardening reads pipeline code from here to drive
      the Packer build; nothing else should touch it
    - kept in sync by scripts/sync_pipeline_repo.sh: fetch + hard-reset +
      clean, once per run, before iteration-0 (refuses if dirty or off main)
    - deliberately separate from any other OSD-Linux-hardened-pipeline
      checkout used for feature-branch dev work (which may be on a
      different branch or have local changes at any time) — /hardening
      never depends on that checkout's state
    - has its own nested `.git` — never let a broad `git add`/`git add -A`
      in the hardening-assist repo touch this folder; it's gitignored
      specifically to prevent that

  hardening-runs/                               <- all run output
                                                    (nested, gitignored — see .gitignore)
    - one timestamped folder per run: <os>_cis_<version>_<date>/
    - <os_name>/exclusions.yaml — the persistent, per-OS exclusion list
      (seeded from this project's exclusions.yaml template on first run)
    - _content_cache/<cis_version>/ — cached ComplianceAsCode/content
      downloads, shared across runs
```

Both `hardening-pipeline-main/` and `hardening-runs/` live nested inside
this project directory (not as siblings) so everything `/hardening` needs
and produces is self-contained under `hardening-assist/` — but they are
**gitignored** and never part of this repo's own history: the pipeline
checkout must stay a pristine, disposable copy of `main` (with its own
nested `.git`), and run output can grow to many GB and must survive
independently, never mixed into this project's commits. See SKILL.md's
Configuration/Guardrails sections for the env-var overrides
(`HARDENING_PIPELINE_DIR`, `HARDENING_RUNS_DIR`, `HARDENING_MAX_ATTEMPTS`)
if any of these need to move again.

## Navigation index

| File | Purpose |
|---|---|
| `CLAUDE.md` | Workspace overview, architecture, hard rules (this file) |
| `.claude/skills/hardening/SKILL.md` | Full `/hardening` step-by-step behavior |
| `.claude/skills/hardening-pr-review/SKILL.md` | Full `/hardening-pr-review` step-by-step behavior (read-only PR gap review) |
| `.claude/hooks/block-pipeline-write.py` | PreToolUse guard denying commit/push in the pipeline checkout |
| `scripts/sync_pipeline_repo.sh` | Fetch + hard-reset + clean the pipeline checkout to `origin/main` |
| `scripts/run_pipeline.sh` | Drive the Packer build for one OS folder |
| `scripts/fetch_content.sh` | Download/verify a pinned ComplianceAsCode/content release datastream |
| `scripts/parse_report.py` | Parse an OpenSCAP HTML report into pass/fail JSON |
| `scripts/lookup_remediation.py` | Check existing/SSG remediation coverage for a rule (read-only) |
| `scripts/check_pr_symmetry.py` | Mechanical remediation/QA/tailoring gap checks on a PR diff (read-only) |
| `exclusions.yaml` | Template for a new OS's persistent exclusion list |
| `README.md` | Short human-facing overview + layout |
