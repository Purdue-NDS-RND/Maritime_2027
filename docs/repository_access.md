# Repository access and branch workflow

Last checked: 2026-11-01. GitHub access is now verified for
`Purdue-NDS-RND/Maritime_2027`. The user authorizes writes exclusively on
`feature/cv-raycast`; this documentation change publishes the shared context there.
No alternate branch, merge or repository-permission change is authorized.

## Current project rule

Read the current branch head before edits and preserve concurrent work. Root and drone
AGENTS.md record this branch restriction for future Codex sessions. Use an expected-head
check for API ref updates; do not force push. The connection can expose wider repository
capabilities, so this working restriction is not a claim of server-enforced branch isolation.

## Access needed for future work

The prior ZIPs were enough for initial review. The current connection supports Git data
operations; only the specified feature ref may be updated. Future connections should
be checked for actual Git-write capabilities, since a source-search connector may be
read-only. Opening a PR or merging is not part of this documentation update.

Select only the intended repository where the connection supports that choice.
For a fine-grained token, the typical proposed capabilities are Contents read/write,
Pull requests read/write and required metadata access, with expiration. Actual supported
operations and organization policies must be checked. Do not send credentials in chat;
configure them through the connection or credential mechanism.

## Branch restriction: what is and is not possible

| Desired restriction | Mechanism and limitation |
| --- | --- |
| Access only selected repositories | Fine-grained PAT or suitably installed GitHub App; verify connection capabilities |
| Work only on sensing branches | Feature-branch workflow is a working rule; server enforcement requires branch protection/rulesets |
| Prevent upstream writes entirely | Grant write only to a separate fork/repository, then review PRs upstream |
| Hide other branches/history | Normal GitHub repository read access is not branch-private |
| Hide/restrict all access outside drone/ | Repository credentials do not provide ordinary directory-level read isolation; use a separate repository for a strict boundary |
| Require review of drone changes | CODEOWNERS plus required reviews; this is review policy, not folder-scoped credential access |

Fine-grained PATs select repositories and capabilities, not a branch allowlist.
A GitHub App installation likewise is not a general branch-only credential.
Branch rules can restrict creation/updates/deletion of selected refs and require PR reviews.
Availability depends on repository visibility, account plan and rule type.

For stronger write confinement, use a separate app/bot identity without admin or bypass
privileges and configure server rules protecting other branches, including future branch
names. Review bypass lists and rule overlap. Reusing the owner's identity can undermine
the intended separation. Protecting main alone still permits changes to other unprotected
branches; it does not mean 'only one branch is writable'.

A fork with no upstream write permission is the simplest clear upstream isolation.
Private fork/org policies can constrain this option, so check the repository settings.

## Proposed team workflow

- Confirm actual upstream owner/repository and current intended base branch; ZIP filename
  feature-cv-raycast is only a snapshot label.
- Work in a focused sensing feature branch or fork. Keep code primarily in drone/ and
  shared definitions only when genuinely common.
- Protect main/default and other integration branches; require review/checks and disable
  force pushes/deletion. Do not grant the coding identity bypass.
- Use focused commits/PRs; review shared/GCS changes with their owners. Preserve boat-only
  acceptance and existing simulator pins. Never force push/delete remote branches here.
- Maintain drone/LLM.md, TASKS.md and relevant docs as behavior/evidence changes.
  Git history holds superseded plans.
- Keep model datasets, recordings, generated engines and logs out of ordinary source
  commits unless the team explicitly chooses an appropriate artifact strategy.

Repository rules and credentials are administered by the repository owner; this document
does not configure them or assert enforcement. AGENTS.md, CODEOWNERS, sparse checkout
and a promise to touch only drone/ are not substitutes for an authorization boundary.

## Primary references

- [Fine-grained personal access tokens: repository selection and permissions](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [Protected branches: requirements, bypass and availability](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [Rulesets: ref creation, updates, deletion and file-path rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)

