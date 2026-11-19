# Automated review is a personal tolerance, not an audit

The maintainer explicitly enabled automated merging/publication of qualifying
stable upstream release updates. Deterministic validation and premerge build tests
are mandatory, but no human reviews each routine qualifying PR.

Claude reviews the complete bounded GitHub source comparison as data, not code
executed on the runner. The configured action is pinned at
`anthropics/claude-code-action@f431adaf77e0fecf918431e75a2b5b45b85af002`.
The action and its runtime/package downloads, the inference provider, model
behavior and API-key custody are additional supply-chain trust dependencies.
Pinning the action does not freeze all downloaded runtime dependencies.

The API/OAuth credential necessarily reaches the action runtime, but is not
included in the review prompt. A supplied read-only GitHub token avoids automatic
exchange for a more privileged GitHub App token; OIDC/write scopes are not given
to the reviewer job. The prompt contains bounded inline evidence, tools are
empty/denied, and no PR checkout is present there. Project/local Claude settings
are not loaded. No action transcript is published as a release artifact.

Prompt injection, model hallucinations, misunderstood changes, false approvals,
and missed vulnerabilities remain possible. A JSON schema validates verdict
shape, not truth. A successful self-test proves integration on synthetic cases,
not that the model will catch all real security issues. The checker also trusts
GitHub's API/signature verification and upstream signing keys. Upstream distribution
tarballs contain generated material that is not byte-identical to Git history;
reviewing a Git comparison does not independently audit all generated/bundled code.

The automatic evidence boundary is intentionally conservative: at most 250
commits, fewer than 300 files, complete text patches, and at most 250 KiB total
serialized evidence. Missing/truncated/binary/oversized evidence blocks the gate.
A release may therefore require human maintenance even if there is no known bug.
Only new stable upstream versions qualify; toolchain/key/workflow/packaging policy
changes and same-version rebuilds do not qualify for bot auto-merge.

Each model assessment has a $3 ceiling and four-turn limit. The integration
self-test performs two assessments: benign approval and dangerous-change rejection.
Budget/time/credential/model failures block merging; the user is responsible for
provider billing and credential rotation. Model identifier: `claude-sonnet-4-6`.

Successful qualifying updates are merged by trusted deterministic code with a
non-forcing fast-forward of the exact tested single-parent commit, not by model
tool calls. A normally advanced main cannot be silently mixed into that commit. A separate trusted-main release
build must pass again; assets upload to a draft before public publication. The
model can neither override metadata constraints nor directly merge/publish.
Repository write/admin access can still modify or bypass the policy; protect it.

Performance builds use ReleaseFast at the maintainer's request: runtime safety
checks are disabled. AI review does not restore them. See SECURITY.md for bundled
library, container, APT, checksum and other security limitations.
