---
name: hardening-pr-review
description: >
  Reviews an open OSD-Linux-hardened-pipeline PR produced by (or in the
  style of) the `/hardening` skill. Invoked as `/hardening-pr-review <pr>`
  (a bare PR number or full GitHub URL). Fetches the PR's diff, description,
  and any existing bot/human review comments, cross-checks the diff against
  this project's hard rules and the `/hardening` skill's guardrails
  (remediation/QA.yaml symmetry, tailoring-vs-remediation-profile scope,
  vendored-datastream edits, PR-description-vs-code drift, run-artifact
  consistency), **always follows up with an actual Packer build + rescan
  against the PR's own branch** to empirically confirm the fix works (not
  just code review), and reports gaps — the same review this project did
  by hand for PR #47 (rocky9.5, CIS 0.1.81). Read-only: never pushes,
  comments, or edits the PR itself; the verification build runs in a
  disposable checkout, never `hardening-pipeline-main`.
---

# /hardening-pr-review — automated hardening-PR gap review

## Invocation

```
/hardening-pr-review <pr_number_or_url> [os_name]
```

Examples: `/hardening-pr-review 47`,
`/hardening-pr-review https://github.com/perforce-osd/OSD-Linux-hardened-pipeline/pull/47`

- Repo defaults to `perforce-osd/OSD-Linux-hardened-pipeline` (this
  project's target pipeline repo — see CLAUDE.md). If a full URL is given,
  parse the owner/repo from it instead.
- `os_name` is optional — only needed to disambiguate when the PR touches
  more than one OS folder, or to pick among several matching run folders
  in Step 3.

This skill is **read-only**: it reports findings in conversation. It never
pushes commits, posts PR comments, or edits files in any checkout. Applying
fixes afterward (as was done for PR #47) is a separate, explicitly-requested
action, not part of this skill.

## Step 1 — Fetch the PR

```
gh pr view <pr> --repo <owner>/<repo> --json title,body,files,commits,baseRefName,headRefName,state
gh pr diff <pr> --repo <owner>/<repo>
gh pr view <pr> --repo <owner>/<repo> --json reviews,comments
gh api repos/<owner>/<repo>/pulls/<pr>/comments   # inline review comments, if any
```

Surface any existing bot review (e.g. Copilot) findings alongside your own
rather than silently re-deriving duplicates of what's already flagged.

## Step 2 — Run the deterministic diff checks

```
gh pr diff <pr> --repo <owner>/<repo> | python3 scripts/check_pr_symmetry.py -
```

This reports, purely mechanically (see the script's own docstring for
exact patterns matched):
- files changed, grouped by OS folder
- remediation tasks/blocks added, with CIS number references
- QA.yaml test blocks added, with CIS number references
- rule idrefs newly tailored out (`selected="false"`) in any
  `harden/*-customization-*.xml`
- any changed file that looks like a raw vendored SSG datastream
  (`ssg-*-ds.xml`, not the customization file) — flag as a **Hard Rule
  violation candidate**: this project's CLAUDE.md forbids hand-editing a
  vendored datastream outside the sanctioned `sed` patches already in
  `perform_hardening.sh`.
- symmetry gaps: a CIS number added to remediation with no matching QA
  test, or vice versa (per `.claude/skills/hardening/SKILL.md` Step 3.2b
  and Step 5 — an excluded/tailored-out rule needs no QA test, since it's
  no longer scanned at all)

Treat every item this script reports as a fact to investigate, not
automatically a bug — e.g. a rule tailored out and *also* missing a QA
test is correct, not a gap (Step 5).

## Step 3 — Judgment-based checks

These require reading actual script/prose content, not just diffing, so
they're instructed here rather than scripted:

1. **Profile/tailoring mismatch.** If Step 2 reports any
   `tailoring_excludes_added` for an OS, open that OS's
   `perform_hardening.sh` (from the PR diff if touched, otherwise the
   pipeline repo at the PR's base) and confirm the remediation loop itself
   — both the per-iteration `oscap xccdf eval` **and** the
   `oscap xccdf generate fix` that derives the auto-remediation playbook —
   use the tailored profile (`$PROFILE_NAME` + `$TAILORING_FILE`), not a
   hardcoded untailored profile like `xccdf_org.ssgproject.content_profile_cis`.
   If it doesn't, the tailoring exclusion only affects the final report,
   not what gets auto-remediated — the excluded rule can still be
   "fixed" during the loop before the tailored profile is ever evaluated.
   This is the exact High-severity gap found in PR #47 before commit
   `431fd9d`.
2. **PR-description-vs-code drift.** For every mechanism the PR body
   claims exists (a script, a systemd unit, a tmpfiles.d drop-in, a sed
   patch, an exclusion, etc.), confirm matching code is actually present
   in the diff — not just described. This is the exact Medium-severity gap
   found in PR #47 before commit `6dc0c30` (description claimed a
   `tmpfiles.d` self-healing mechanism that hadn't been committed).
3. **Run-artifact cross-reference.** If an OS/CIS-version pair can be
   inferred from the changed paths (and `os_name` if given), look for a
   matching `hardening-runs/<os_name>_cis_<version>_<date>/` folder (there
   may be more than one — prefer the most recent, or ask via
   `AskUserQuestion` if ambiguous and `os_name` doesn't disambiguate it).
   Compare its `remediations_applied.md` / `SUMMARY.md` against the PR
   diff — flag anything the run recorded as applied that isn't actually
   present in the diff (this is the run-output side of the same
   description-vs-code drift check, and would have caught the same PR #47
   gap independently of reading the PR body).

## Step 4 — Empirical build verification (always, not optional)

Static review (Steps 2-3) cannot catch runtime-only failures — e.g. a
regex that doesn't actually match the real XML a script parses, an
`oscap`/Packer command that only breaks inside the build VM, a tmpfiles
rule that doesn't apply the way its comment claims. PR #47 itself is a
case in point: the profile/tailoring fix and tmpfiles.d fix were both
merged on code review alone, with no Packer build ever confirming they
work — that gap is exactly what this step exists to close. So: **always
run an actual build+rescan against the PR's own branch before finishing a
review**, not just when the diff looks build-logic-heavy.

The PR's changes are almost certainly unmerged (still on its head branch),
so this cannot use `hardening-pipeline-main` (Step "Syncing the pipeline
repo" in `.claude/skills/hardening/SKILL.md` only ever resets that
checkout to `origin/main`, and refuses to run dirty/off-main — by design,
never touch it here). Instead:

1. Get a disposable checkout of the PR's exact head commit:
   ```
   git clone --branch <headRefName> --single-branch \
     https://github.com/<owner>/<repo>.git <scratch_dir>/pr-<n>-verify
   ```
   (`<headRefName>` from Step 1's `gh pr view --json ... headRefName`;
   `<scratch_dir>` is this session's scratchpad, not anywhere inside this
   project — it's build-only and disposable, same spirit as
   `hardening-pipeline-main` but per-review, not shared). If a local
   checkout already sitting on that exact branch/commit is available and
   convenient (as happened for PR #47), reusing it instead of a fresh
   clone is fine — the constraint is "build from the PR's real code",
   not "always clone fresh".
2. Run the same primitives `/hardening` itself uses, pointed at that
   checkout instead of `hardening-pipeline-main`:
   ```
   scripts/run_pipeline.sh <scratch_dir>/pr-<n>-verify <os_name> \
     <runs_dir>/<os_name>_cis_<version>_pr<n>-verify_<date>/iteration-0 <cis_version>
   python3 scripts/parse_report.py <that iteration's hardened report> \
     <runs_dir>/<os_name>/exclusions.yaml
   ```
3. Run this in the background (a real build takes tens of minutes — see
   `/hardening` SKILL.md Step 1) and report back when it completes: did
   the build itself succeed (catches e.g. a `RESULT_ID`-style resolution
   failure aborting the script), and does the parsed result show the
   expected state (every rule PASSED or EXCLUDED, in particular the rule(s)
   this PR touches).
4. This run's output is disposable verification, not a real
   `/hardening` run record — don't confuse it with one in Step 3's
   run-artifact cross-reference (that step reads *existing* run folders
   from real `/hardening` runs, it doesn't consume this one).

## Step 5 — Report

Report gaps in the same style used for PR #47: severity-tagged
(High/Medium/Minor), each anchored to a file (and line, where the diff
gives one) with a concrete failure scenario — not a generic checklist
dump. Explicitly note anything from Step 2 that looked like a gap but
turned out correct per project convention (e.g. an excluded rule
correctly missing a QA test), so it isn't mistaken for something
overlooked. Include Step 4's build result explicitly — "reviewed, and
verified via an actual build" is a materially stronger statement than
"reviewed" alone, and the report should say which one this is.

## Guardrails

- Never push, comment on, or edit the PR — this skill only reports.
- Never treat `scripts/check_pr_symmetry.py`'s output as ground truth on
  its own; every flagged item still needs the Step 3 judgment pass before
  being reported as a real gap (or being reported as correctly-fine).
- Don't re-derive a finding an existing bot/human review already made —
  cite it instead of duplicating it.
- Step 4's scratch checkout is build-only, same as
  `hardening-pipeline-main` — never `git commit`/`git push` in it, for
  any reason.
- If asked to also fix what's found, treat that as a new, separate,
  explicitly-requested task — same as the PR #47 follow-up commits — not
  something this skill does on its own.
