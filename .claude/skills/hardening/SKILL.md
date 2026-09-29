---
name: hardening
description: >
  Automates the OSD-Linux-hardened-pipeline CIS hardening loop for one OS.
  Invoked as `/hardening <OS_NAME> <CIS_VERSION>` (e.g. `/hardening rocky8.10
  3.0.0`): builds the hardened image, scans it, auto-remediates every FAILED
  benchmark not already excluded, and loops (rebuild -> rescan) until every
  benchmark is PASSED or EXCLUDED. Use when asked to run, automate, or extend
  the CIS hardening pipeline for a specific OS/benchmark version.
---

# /hardening — automated CIS hardening loop

## Invocation

```
/hardening <OS_NAME> <CIS_VERSION>
```

Example: `/hardening rocky8.10 0.1.81`

- `OS_NAME` must match a folder name in the pipeline repo (see Configuration)
  — e.g. `rocky8.10`, `rocky9.5`, `alma8.10`, `alma9.5`, `debian12`,
  `ubuntu22.04`, `ubuntu24.04`. If it doesn't match, list the available
  folders and stop.
- `CIS_VERSION` is a **[ComplianceAsCode/content](https://github.com/ComplianceAsCode/content/releases)
  release tag** (e.g. `0.1.81`), *not* the CIS benchmark document edition.
  ComplianceAsCode is the upstream project that produces the SCAP datastream
  (`ssg-*-ds.xml`) actually used to scan/remediate — this argument pins
  exactly which upstream release's datastream to use, instead of whatever
  the OS folder relies on by default (the distro-packaged
  `scap-security-guide` RPM for Rocky/Alma today, or whatever happens to
  already be vendored in `harden/` for Debian/Ubuntu). See "Pinning SCAP
  content" below. If omitted, the OS folder's existing default is used
  unchanged.
  - Upstream product-name mapping (rocky/alma 8.x share RHEL8 content
    upstream, there's no dedicated "rl8"/"almalinux8" product):
    `rocky8.9`/`rocky8.10`/`alma8.10` → `ssg-rhel8-ds.xml`,
    `rocky9.5` → `ssg-rhel9-ds.xml`, `alma9.5` → `ssg-almalinux9-ds.xml`,
    `debian12`/`ubuntu22.04`/`ubuntu24.04` → their own matching product.
  - Not every release tag has meaningfully updated content for every OS
    (e.g. v0.1.82 didn't add anything new for RHEL8 — it was mostly an
    Ubuntu-focused release). Don't assume a higher version number means
    newer content for the specific OS being hardened; if in doubt, diff
    the fetched datastream against what's already vendored/installed
    before treating a version bump as meaningful.

## Host prerequisites

Before Step 1's first iteration on a machine that hasn't run `/hardening`
before (or if the build fails on a missing tool/`/dev/kvm`/KVM
acceleration), run:

```
scripts/setup_host.sh
```

It installs/verifies `qemu-kvm`, `packer` + its qemu plugin,
`oscap`/`scap-security-guide`, `ansible-playbook`, and Python3+PyYAML, and
confirms KVM acceleration is actually usable (not just installed) — see
README.md Requirements. It's idempotent and safe to re-run, so default to
running it once up front rather than waiting for a build to fail first. It
does not stage per-OS base images — see Step 1.

## Configuration

| Setting | Default | Override |
|---|---|---|
| Pipeline repo | `<hardening-assist>/hardening-pipeline-main` | `$HARDENING_PIPELINE_DIR` |
| Pipeline repo clone URL | `git@github.com:perforce-osd/OSD-Linux-hardened-pipeline.git` | `$HARDENING_PIPELINE_REPO_URL` |
| Runs directory | `<hardening-assist>/hardening-runs` | `$HARDENING_RUNS_DIR` |
| Max remediation attempts per rule (N) | `3` | `$HARDENING_MAX_ATTEMPTS` |

`<hardening-assist>` is this project's own directory. Both are nested
inside it (not siblings) but are gitignored and never part of this
project's own commit history — see CLAUDE.md's Architecture section.

The pipeline repo is a **dedicated, automation-only checkout of `main`**,
separate from any other working checkout of `OSD-Linux-hardened-pipeline`
(e.g. one used for feature-branch dev work, which may be switched to a
different branch or have local changes at any time). `/hardening` only
ever reads pipeline code from this checkout to drive the Packer build —
see "Syncing the pipeline repo" below.

## Pinning SCAP content (optional, driven by CIS_VERSION)

`scripts/run_pipeline.sh` takes `cis_version` as an optional 4th argument.
When given, before the Packer build it:

1. Runs `scripts/fetch_content.sh <cis_version> <os_name> <content_cache_dir>`
   — downloads (or reuses a cached) `ComplianceAsCode/content` release
   tarball, **verifies its sha512 checksum**, and extracts just the one
   datastream file needed for this OS (see the product-name mapping above).
   The cache is shared across OSes/runs at the same version
   (`<runs_dir>/_content_cache/<cis_version>/`), so this only downloads the
   ~175MB tarball once per version, not once per run.
2. Copies that extracted file into `<os_dir>/harden/` (e.g.
   `rocky8.10/harden/ssg-rhel8-ds.xml`) — **untracked**, removed again after
   the build finishes (via a trap), so it never lingers as an uncommitted
   change in the pipeline repo.
3. For Rocky/Alma, `perform_hardening.sh` has a small additive hook: if
   `/tmp/harden/ssg-rhel8-ds.xml` (the uploaded staged file) exists, it's
   used in place of the distro-packaged datastream and the
   `scap-security-guide` RPM install/removal is skipped entirely. If it
   doesn't exist (no `cis_version` given), behavior is byte-for-byte
   unchanged from before — this is opt-in, not a replacement of the
   existing default. Debian/Ubuntu already vendor their own datastream in
   `harden/`, so staging a fetched one there is a drop-in replacement with
   no script changes needed.

This is the same vendoring pattern as the abandoned `8bab0da` attempt
(vendor into `harden/`, point `perform_hardening.sh` at it), but pinned to
a version the user has confirmed actually has meaningful content for the
OS in question, fetched fresh each time rather than committed as a
472,000-line diff into the pipeline repo.

## Syncing the pipeline repo

Before Step 1's first iteration (not on every subsequent iteration of the
same run — the checkout doesn't change mid-run), run:

```
scripts/sync_pipeline_repo.sh <pipeline_dir>
```

This fetches `origin/main` into the dedicated pipeline checkout and does a
`git reset --hard origin/main` + `git clean -fdx`, so every run starts from
the exact latest `main` with no leftover build artifacts from a prior run.
It refuses to run (errors out) if `<pipeline_dir>` isn't currently on
`main` — that would mean something other than this skill touched it, and
it should be investigated rather than silently reset.

**First run on a new machine:** if `<pipeline_dir>` doesn't exist yet, the
script clones it itself (single-branch, `main`) from the pinned URL in the
Configuration table above — never ask the user for this URL or guess one;
it's already checked into this project specifically so first-time setup
on a fresh machine doesn't need it re-supplied. Only fall back to asking
the user if `$HARDENING_PIPELINE_REPO_URL` is explicitly needed to point
at a different remote (fork, HTTPS instead of SSH, etc.).

**Never `git commit` or `git push` in this checkout, ever, for any reason**
— it exists purely so `/hardening` has a stable, isolated source of
pipeline code to build from. See Guardrails.

## Step 1 — Run the base pipeline

Run `scripts/run_pipeline.sh <pipeline_dir> <os_name> <runs_dir>/<os_name>_cis_<cis_version>_<date>/iteration-0 <cis_version>`.

This drives the **existing** Packer build for that OS folder
(`config.pkr.hcl` → cloud-init → upload harden files → `perform_hardening.sh`
→ baseline scan → 2-iteration SSG auto-remediation → custom
`remediation-playbook.yml`/`remediation_script.sh` → final tailored scan).
Do not reimplement any of that — it already produces:

- **Report format: HTML** — `harden-scan-results/report_perforce_CIS_hardened.html`
  (OpenSCAP XCCDF evaluation report against the tailored
  `xccdf_com.perforce.content_profile_cis_customized` profile). This is the
  report Step 2 parses. A `report_perforce_CIS_unhardened.html` baseline is
  also produced for reference but is not part of the loop.
- The built image: `output/<os>-x86_64.qcow2`.
- `remediation-scripts.zip` (the playbooks/scripts actually applied).

A single build takes real time (Packer boots a VM, runs cloud-init, installs
packages, scans twice) — expect this to run for tens of minutes, not
seconds.

## Step 2 — Parse results

```
python3 scripts/parse_report.py <hardened_report.html> <runs_dir>/<os_name>/exclusions.yaml
```

Outputs JSON: per-rule `rule_id`, `title`, `cis` control number(s), for every
rule not in `pass`/`notapplicable`/`fixed` state, with anything already in
the exclusion list filtered out (`excluded_skipped`). The exclusion list
used here is the **persistent, per-OS** one — see Step 5, not the template
in this skill's own repo.

## Step 3 — Remediation loop

For **all** currently-failing, non-excluded rules together (not one rebuild
per rule — a full Packer build is expensive; batch every iteration):

1. **Identify the remediation source**, per rule:
   ```
   python3 scripts/lookup_remediation.py <pipeline_dir> <os_name> <rule_id>
   ```
   This reports facts only (it writes nothing):
   - `existing_coverage`: does `remediation-playbook.yml`
     (Ansible, RPM-family OSes) or `remediation_script.sh` (bash,
     Debian/Ubuntu) already reference this rule? If yes and it's still
     failing, the existing custom fix is not working — flag this
     explicitly rather than silently re-adding a duplicate task.
   - `datastream_check`: does the SCAP Security Guide datastream for this
     OS embed an `ansible`/`sh` `<fix>` for this rule? (Only checkable when
     a datastream is reachable — vendored in `harden/` for Debian/Ubuntu,
     or an installed `scap-security-guide` package on this host for
     Rocky/Alma. When unavailable, this comes back `available: false` —
     that is not the same as "no fix exists", just "can't tell from here".)

   Then **follow `TECHNICAL_GUIDE.md` in the pipeline repo** (its
   "Hardening Process" and "SCAP Tailoring Files" sections cover exactly
   this task — `REMEDIATION_PERSONA.md`/`HARDENING_PROCESS.md` are stale
   references from an earlier pipeline-repo layout and no longer exist on
   `main`) to decide and write the actual remediation:
   - If SSG already ships a fix and the base pipeline's own 2-iteration
     auto-remediation should have applied it but the rule still fails,
     that's a signal of an environment quirk (cloud-init/container false
     positive, ordering issue, an SSG ansible fix's own `when` condition
     not holding on this image, a fix that only exists for a different
     `<fix system=...>` type than the pipeline generates) — investigate the
     actual datastream `<fix>` content and its conditions before adding a
     redundant custom task; check `perform_hardening.sh`'s existing
     OVAL-check `sed` patches for precedent.
   - If no fix exists anywhere (SSG nor custom playbook) and the rule is
     inapplicable to this image's design (e.g. GNOME/partitioning-style
     rules per TECHNICAL_GUIDE.md's "SCAP Tailoring Files" section /
     the OS's own tailoring file), that's a candidate for **exclusion**,
     not remediation — do not force a fix for something structurally
     inapplicable. A rule with no shipped fix is not automatically
     inapplicable, though — if it's a real, checkable condition (e.g. a
     filesystem-ownership sweep), write a hand-written task instead.
   - Otherwise, add a hand-written Ansible task (RPM-family) or bash block
     (Debian/Ubuntu) to that OS's remediation file, matching existing
     style/tagging exactly (see `remediation-playbook.yml` for the tag
     convention — CIS number, DISA-STIG/NIST-800-53/PCI-DSS tags, severity/
     complexity/disruption tags — and comment style like `#benchmark X.Y.Z`
     in `remediation_script.sh`). Keep it idempotent (safe to re-run).

2. **Apply** — the edit to `remediation-playbook.yml` / `remediation_script.sh`
   *is* the application; the fix lands on the next rebuild (this pipeline
   always builds fresh from a stock base image, it never patches a running
   image in place).

2b. **Add a QA.yaml regression test** — for every rule that got a
    hand-written remediation task this iteration (not for rules already
    covered by SSG's own fix, and not for rules that only needed an
    exclusion), add a matching test block to that OS folder's `QA.yaml`,
    matching existing style exactly (`name:` prefixed with the CIS number,
    a `shell`/`stat` check registered into a variable, a `debug` on the
    result, `failed_when` on the actual pass/fail condition, `tags` —
    see the `7.1.12` ownership blocks or `3.2.2` log-check block in
    `QA.yaml` for precedent). This is what lets the CI "Testing" job
    (`QA.py`/`QA-qcow2.sh` running `QA.yaml` against the built VMDK/QCOW2 —
    see `TECHNICAL_GUIDE.md`'s "Testing Framework" section) catch a
    regression on this specific rule later, independent of the SCAP scan.
    Keep it read-only/non-mutating like the existing blocks — `QA.yaml`
    verifies, it doesn't remediate. Leave this as an uncommitted diff
    alongside the remediation file, same as it.

3. **Rebuild and rescan** — run `scripts/run_pipeline.sh` again into
   `iteration-<n+1>`.

4. **Re-check** — re-run `scripts/parse_report.py` against the new report.
   For every rule that was targeted this iteration: PASSED → done;
   still FAILED → increment its attempt counter.

Track attempt counts per `rule_id` across iterations in
`<run_dir>/attempt_counts.json` (a simple `{rule_id: count}` map you
maintain directly).

**Stop condition per rule**: once a rule's attempt counter reaches `N`
(default 3) and it is still failing, **stop looping on that rule** — other
still-failing rules continue. Use `AskUserQuestion` to ask whether to:
- add it to the exclusion list (with a reason) — see Step 5 for what this
  entails (it's not just the `exclusions.yaml` entry), or
- leave it for manual escalation (record as such, don't add to exclusions,
  don't keep retrying it either).

Never add to the exclusion list without a reason, and never remove or
weaken an existing entry without being asked.

## Step 4 — Completion criteria

The run is complete only when the latest report shows, for every rule:
**PASSED**, or **EXCLUDED** (present in the exclusion list with a reason).
Zero rules may be left in FAILED state. If any rules are stuck at manual
escalation (declined exclusion in Step 3), the run ends but is reported as
**incomplete**, not failed — summarize exactly which rules and why.

## Step 5 — Exclusion list

Persistent, per-OS, **outside** both this skill's folder and the timestamped
run-output folders (so it survives across runs and isn't overwritten):

```
<runs_dir>/<os_name>/exclusions.yaml
```

- First run for a given OS: if this file doesn't exist yet, seed it by
  copying this skill's `exclusions.yaml` template.
- Read before Step 2 filters failed benchmarks (already wired into
  `parse_report.py`'s second argument).
- The user can hand-edit it any time; never regenerate it wholesale —
  only ever append/amend individual entries.
- Copy a snapshot of it into each run's output folder (Step 6) for the
  record, but the snapshot is not the source of truth for the next run.

Format: see this skill's `exclusions.yaml` for the schema
(`rule_id`, `reason`, `added`, `attempts_exhausted`).

**Adding a rule here also means tailoring it out of the scan itself**:
whenever a rule is added to `exclusions.yaml` (Step 3's stop condition),
also add a matching `selected="false"` entry for it to the OS's own SCAP
tailoring file (`harden/*-customization-perforce-CIS.xml` — see
`TECHNICAL_GUIDE.md`'s "SCAP Tailoring Files" section for the entry
format), so it's genuinely excluded from the scan going forward, not just
filtered out of `parse_report.py`'s output after the fact. Both edits are
one action, not two independent lists to keep in sync by hand. This is
also why an excluded rule needs no Step 3/2b `QA.yaml` test — it's no
longer scanned/remediated at all, so there's nothing for a regression test
to guard. Don't duplicate a rule that's already tailored out into
`exclusions.yaml` either; it won't show up as FAILED in the report in the
first place.

## Step 6 — Output storage

```
<runs_dir>/<os_name>_cis_<cis_version>_<YYYY-MM-DD>/
├── iteration-0/                 # scripts/run_pipeline.sh output, per iteration
├── iteration-1/
├── ...
├── report_perforce_CIS_hardened.html    # copy of the LATEST iteration's
├── report_perforce_CIS_unhardened.html  # reports, at top level for easy access
├── remediation-playbook.yml             # (or remediation_script.sh for
│                                         # Debian/Ubuntu) — the copy of
│                                         # the OS folder's remediation file
│                                         # as it stood for the latest
│                                         # iteration, whether or not it
│                                         # was edited this run
├── QA.yaml                              # ditto for the OS folder's QA
│                                         # test playbook (Step 3, sub-step
│                                         # 2b), whether or not it was
│                                         # edited this run
├── <os>-customization-perforce-CIS.xml  # ditto for the SCAP tailoring file
│                                         # (e.g. ssg-rl8-ds-customization-
│                                         # perforce-CIS.xml)
├── attempt_counts.json
├── exclusions_snapshot.yaml     # copy of the exclusion list as of this run
├── image_reference.txt          # path + sha256 of the final qcow2 (not a
│                                 # copy — these images are ~2GB, reference
│                                 # them in place)
├── remediations_applied.md      # one entry per rule fixed this run: rule
│                                 # id, cis number, what was added, which
│                                 # file(s) — including the QA.yaml test
│                                 # block, if one was added for that rule
└── SUMMARY.md                   # final compliance state: pass/excluded/
                                  # escalated counts, pointer to the final report
```

The top-level `report_*.html`, `remediation-playbook.yml`/`remediation_script.sh`,
`QA.yaml`, and `*-customization-perforce-CIS.xml` copies are refreshed after
every iteration (not just the last one) — copy them from the OS folder into
the run root as soon as that iteration's build finishes, alongside the usual
per-iteration copies under `iteration-<n>/`. This keeps the run-folder root
showing the current-best state at a glance without having to dig into the
latest `iteration-<n>/` subfolder, and preserves history of prior
iterations' versions of these files.

`<runs_dir>` defaults to `<hardening-assist>/hardening-runs`, nested
inside this project directory alongside the pipeline checkout, but
gitignored — see CLAUDE.md's Architecture section.

## Guardrails

- **Never `git commit` or `git push` in the pipeline repo
  (`OSD-Linux-hardened-pipeline`), full stop, no exceptions** — this
  applies to the dedicated `<pipeline_dir>` checkout at least as strongly
  as it did to any other checkout: that folder exists solely so
  `/hardening` has a stable copy of `main` to build from, never to
  accumulate commits of its own. Leave the edited
  `remediation-playbook.yml`/`remediation_script.sh` and `QA.yaml` as an
  uncommitted diff for review.
- Only `scripts/sync_pipeline_repo.sh` may fetch/reset/clean
  `<pipeline_dir>`, and only once per run, before iteration-0 (see "Syncing
  the pipeline repo"). It refuses to run if the checkout is dirty, to
  avoid silently destroying a previous run's uncommitted remediation diff
  — if that happens, surface it to the user rather than forcing past it.
- Don't hand-edit the vendored/installed SSG datastream XML — the only
  sanctioned datastream edits are the existing OVAL-check `sed` patches
  already in `perform_hardening.sh`.
- Don't weaken or remove an existing documented exclusion (tailoring file
  `selected="false"` entries, or entries already in
  `<runs_dir>/<os_name>/exclusions.yaml`) to force a pass.
- Preserve the pipeline's 2-iteration auto-remediation loop inside
  `perform_hardening.sh` — this skill's loop wraps around it, it doesn't
  replace it.
- If `scripts/lookup_remediation.py`'s datastream check comes back
  `available: false` for an RPM-family OS other than the one whose SSG
  package happens to be installed on this host, say so plainly rather than
  guessing — the real check may need to happen inside a running build VM.
