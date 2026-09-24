# hardening-assist

A standalone Claude Code project (sibling to `ol-cve-assist`) that automates
the CIS hardening loop for `OSD-Linux-hardened-pipeline`: build the hardened
image, scan it, remediate every failing benchmark not already excluded, and
repeat until everything is PASSED or EXCLUDED.

`cd` into this project and run Claude Code here directly — `/hardening` is
available as soon as the session starts. See `CLAUDE.md` for the always-loaded
workspace context (pipeline architecture, hard rules) and
`.claude/skills/hardening/SKILL.md` for the full step-by-step skill behavior.

This project holds only the skill definition, its helper scripts, and
config — not the pipeline codebase itself (that's the separate, dedicated
`hardening-pipeline-main` checkout — see CLAUDE.md) and not any run output
(that's `hardening-runs/`, also outside this project).

## How it works

When you run `/hardening <OS_NAME> <CIS_VERSION>`:

1. **Sync the pipeline checkout** — `scripts/sync_pipeline_repo.sh` fetches
   `origin/main` into the dedicated `hardening-pipeline-main` checkout and
   hard-resets/cleans it. Refuses if it's not on `main` or has uncommitted
   changes (protects any leftover remediation diff from a prior run).

2. **Build & scan** — `scripts/run_pipeline.sh` drives the existing Packer
   pipeline for that OS folder: cloud-init → (optionally) stage the pinned
   `CIS_VERSION` SCAP datastream via `fetch_content.sh` → `perform_hardening.sh`
   → baseline scan → SSG's own 2-iteration auto-remediation → custom
   `remediation-playbook.yml`/`remediation_script.sh` → final tailored scan.
   Produces the HTML report + built `.qcow2`. Takes tens of minutes.

3. **Parse results** — `scripts/parse_report.py` reads that report against
   the OS's persistent `exclusions.yaml`, returning every rule that's still
   failing and not already excluded.

4. **Remediate** — for all failing rules together (not one rebuild per rule):
   `scripts/lookup_remediation.py` checks whether SSG or the custom playbook
   already covers it, then the actual fix is written/adjusted per
   `REMEDIATION_PERSONA.md`/`HARDENING_PROCESS.md` in the pipeline repo, or
   flagged as a candidate for exclusion if structurally inapplicable.

5. **Rebuild and repeat** — back to step 2 for `iteration-<n+1>`, tracking
   per-rule attempt counts. Once a rule hits `HARDENING_MAX_ATTEMPTS`
   (default 3) still failing, the loop stops on that rule and asks whether
   to exclude it (with a reason) or leave it for manual escalation. The run
   ends only when every rule is PASSED or EXCLUDED.

6. **Store results** — everything lands under
   `hardening-runs/<os>_cis_<version>_<date>/`: per-iteration subfolders plus
   always-current top-level copies of the report/remediation files/tailoring
   XML, `attempt_counts.json`, `exclusions_snapshot.yaml`,
   `image_reference.txt`, `remediations_applied.md`, and a final `SUMMARY.md`.

See `.claude/skills/hardening/SKILL.md` for the full detail behind each step.

## Layout

```
CLAUDE.md                           always-loaded workspace context
.claude/skills/hardening/SKILL.md   the skill definition Claude follows
.claude/hooks/block-pipeline-write.py  PreToolUse guard: denies git commit/push
                                        targeting the pipeline checkout
scripts/
  sync_pipeline_repo.sh             fetches/resets the dedicated pipeline checkout to origin/main
  run_pipeline.sh                   drives the existing Packer build for one OS folder
  fetch_content.sh                  downloads/verifies a pinned ComplianceAsCode/content release
  parse_report.py                   parses an OpenSCAP HTML report into pass/fail JSON
  lookup_remediation.py             checks existing/SSG remediation coverage for a rule
exclusions.yaml                     template for a new OS's persistent exclusion list
```

## Usage

```
/hardening <OS_NAME> <CIS_VERSION>
```

Example: `/hardening rocky8.10 3.0.0`

See `SKILL.md` for the full step-by-step behavior, configuration
(`HARDENING_PIPELINE_DIR`, `HARDENING_RUNS_DIR`, `HARDENING_MAX_ATTEMPTS`),
and guardrails.

## Requirements

Whatever machine runs this needs everything the base pipeline already
needs: `packer`, `oscap`/`scap-security-guide` (or the OS's vendored
datastream under `harden/`), `ansible-playbook`, and Python 3 with
`PyYAML`.

## Testing the helper scripts standalone

```
python3 scripts/parse_report.py /path/to/report_perforce_CIS_hardened.html
python3 scripts/lookup_remediation.py /path/to/OSD-Linux-hardened-pipeline rocky8.10 <rule_id>
```

Both print JSON and don't modify anything.
