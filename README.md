# ghostty-debian

Independent personal **Ghostty** packages for **Debian 13 (trixie), amd64**.
Not an official Ghostty or Debian package, APT repository, or supported
redistribution service. Current inputs are in [`release.conf`](release.conf).

> **zervin's personal risk tolerance:** I maintain this for my own use and my own
> risk tolerance. My willingness to run these builds is not a recommendation
> that you trust them. Your requirements may be different; review the code,
> inputs, and build records yourself, or use a distribution package you trust.
> I promise neither security, timely updates, nor reproducible builds.

[Releases](https://github.com/zervin/ghostty-debian/releases) ·
[Build CI](https://github.com/zervin/ghostty-debian/actions/workflows/release.yml) ·
[Upstream checks](https://github.com/zervin/ghostty-debian/actions/workflows/check-upstream.yml) ·
[Claude gate](https://github.com/zervin/ghostty-debian/actions/workflows/gated-update.yml)

## How releases work

1. Daily at **08:23 UTC**, or on manual dispatch, GitHub finds new stable
   upstream `vX.Y.Z` tags (not `tip`, `vt-*`, or prereleases).
2. A GitHub-verified annotated tag is required. CI opens a bot PR pinning its
   source commit/URL and Debian version. Zig, signing keys, build image and
   packaging infrastructure stay unchanged.
3. The explicitly dispatched gate accepts **only** a same-repository,
   single-commit `github-actions[bot]` PR changing exactly `release.conf` and
   `debian/changelog` in the generated format, based on current `main`.
4. Before merging, a separate read-only job builds verified source **offline**,
   runs lintian, and tests clean Debian installation/configuration/resources/purge.
5. Claude reviews the metadata and complete, bounded upstream source comparison.
   It must explicitly approve the **exact tested head**, mark its review complete,
   and report no high/critical security or blocking correctness/licensing/merge
   findings. Missing credentials, errors, malformed/stale reviews, incomplete
   diffs, binary changes or oversized evidence **block** automation.
6. A separate trusted job revalidates the PR/base/head and integrates only the
   exact tested, single-parent commit using a **non-forcing fast-forward**. If
   main advanced, integration fails rather than mixing in untested changes.
   It confirms the PR is merged and explicitly dispatches the release build: `GITHUB_TOKEN`
   merges do not otherwise trigger push workflows.
7. GitHub builds/tests the merged commit, verifies artifact checksums, uploads
   everything to a draft, then publishes it **only after all uploads succeed**.

Routine qualifying release updates need no manual approval. Compiler, key,
workflow, infrastructure and packaging-policy changes remain manual. A failed
or uncertain gate requires investigation; it is never interpreted as approval.
New releases can require maintenance (including compiler changes); this is not
an unconditional promise to publish every tag. Current review limits include
250 commits, fewer than 300 text-changed files and 250 KiB serialized evidence.

Claude's structured verdict is the approval signal, not an unrestricted agent
or a formal GitHub self-approval by the PR author. The model has no merge/write
authority; deterministic trusted code owns the merge and publication decisions.
An AI review is **not a security audit**, and prompt injection/false negatives
remain possible. See [SECURITY.md](SECURITY.md).

Human pushes/merges and manual dispatch on trusted `main` can also build/publish
packaging changes; write access is an explicit trust boundary. Do not grant it
to contributors whose changes you would not run and publish.

## Reviewer setup and tests

Configure exactly one repository Actions secret: `ANTHROPIC_API_KEY` or
`CLAUDE_CODE_OAUTH_TOKEN`. Never put credentials in Git or a PR. The pinned
Claude Action receives a read-only GitHub token, no tools, bounded inline source
evidence, and no PR checkout in its credential-bearing job. Each assessment has
a **$3 maximum budget** and four-turn limit; exhausting either blocks approval.
The action/runtime and inference service remain trusted dependencies.

Enable GitHub Actions PR creation in repository settings. An existing automation
branch is never overwritten; open PRs can be retried by the next upstream check.
If `main` advanced, regenerate/rebase the metadata PR and rerun all gates.

Run a real **bot-dispatched** reviewer integration self-test (clean approval +
dangerous-change rejection; **never merges or publishes**):

```sh
gh workflow run check-upstream.yml --repo zervin/ghostty-debian --ref main -f reviewer_self_test=true
```

For manual recovery, the update gate accepts `pr_number` and `expected_head_sha`
inputs; these are assertions to independently verify, not authorization to merge
an arbitrary PR. Never bypass a failed reviewer by substituting a success JSON.

## Build mode and package policy

The initial `1personal1` build used **ReleaseSafe**. Ghostty labels both `.debug`
and `.safe` as debug in its banner, so that banner did not mean an unoptimized
Debug build. At the maintainer's request, `1personal2` and newer use upstream's
recommended **ReleaseFast** distribution mode (`.fast`). This removes the banner
and prioritizes performance, but **disables Zig runtime safety checks**. CI
checks the installed binary's actual build mode, not just the requested flags.

Other choices: baseline CPU, PIE, Sentry disabled, emitted docs, unchanged
upstream code, version derived from Debian changelog. Layer-shell is private in
`/usr/lib/ghostty`, resolved only by `$ORIGIN/../lib/ghostty`; build/working-directory
RUNPATH entries are removed. Development headers/static archives and the
separate VT library are not shipped. Debhelper derives runtime dependencies.
No handwritten maintainer scripts or alternatives registration are supplied.

Four exact lintian `embedded-library` exceptions retain upstream FreeType,
libpng, libxml2 and zlib. These copies **do not receive Debian library security
updates**; monitoring upstream and rebuilding is my responsibility. Other
lintian errors fail CI. Initial warnings were two groff line-adjustment warnings
in generated manuals. Licenses/notices are preserved heuristically, not audited.

Debian revision filenames use `.deb13u1`, not `~deb13u1`: GitHub rewrites `~`
in asset names, which would otherwise invalidate downloaded checksum entries.

## Install

Your laptop needs neither Docker nor a compiler for normal use. Download the
`.deb` and `SHA256SUMS` from a successful release. For example:

```sh
gh release download --repo zervin/ghostty-debian --dir ghostty-download \
  --pattern '*_amd64.deb' --pattern SHA256SUMS
cd ghostty-download
sha256sum --check --strict --ignore-missing SHA256SUMS
sudo apt install ./ghostty_1.4.0-1personal2.deb13u1_amd64.deb
ghostty +version
# Optional removal:
sudo apt purge ghostty
```

Use the exact downloaded filename for later releases. Checksums detect differing
files relative to the downloaded list; they do not independently authenticate a
compromised uploader. Do not pipe downloaded scripts into a shell. There is no
APT repository or automatic update of your installed package. Check for existing
packages named `ghostty` before replacing them. Only trixie/amd64 is supported.

## Optional local staging/debugging

The same scripts run in hosted CI; local compilation is optional. Prerequisites:
Linux amd64, Docker/Buildx, Git, Bash, Python 3, ShellCheck, RAM and disk space.
Docker access is effectively host-root access. Use a disposable host and a clean
checkout without credentials or personal files.

```sh
git clone https://github.com/zervin/ghostty-debian.git
cd ghostty-debian
bash tests/static.sh
bash scripts/build.sh
```

Work/output directories must initially be empty. Preserve old records and use
fresh directories to repeat:

```sh
WORK_DIR="$PWD/.work/second" OUTPUT_DIR="$PWD/artifacts-second" bash scripts/build.sh
```

Source and Zig signatures are checked before extraction, and source `VERSION`
must match the requested release. Fresh `zig build --fetch=all` verifies
manifest hashes and populates local `zig-pkg` without running build steps. Bare
URL fetch with Zig 0.17.1 has an observed archive-wrapper cache bug; normal
build-fetch avoids it without replacing hashes or custom extraction. An offline
regression recomputes libxev's declared hash in a separate fresh cache.

Compilation runs as uid 1000, read-only root/checkout, no capabilities and
`--network none`. No host home, SSH agent, credential or Docker socket is passed
to the compiler. Online preparation still processes upstream dependencies; the
runtime installation test is root inside a disposable Debian container with APT
network access. Containers are not a kernel/daemon escape-proof sandbox.

Assets include `.deb`, `.buildinfo`, `.changes`, `SHA256SUMS`, input signatures
and observed hashes, dependency file hashes, logs, inventory, image metadata,
and package contents/control records. These aid inspection, not reproducibility.
Base images and Actions are SHA pinned, but signed Debian APT inputs and some
Claude runtime dependencies move. No binary/changes signature or SLSA claim.

## Origins and limitations

[ghostty-org/ghostty](https://github.com/ghostty-org/ghostty) is authoritative
application source. [mkasberg/ghostty-ubuntu](https://github.com/mkasberg/ghostty-ubuntu)
is established broader Ubuntu/Debian packaging with PPA support. This independent
repository is a narrower personal maintenance/trust choice, not evidence that
another maintainer is malicious. Scripts here are original MIT-licensed work;
upstream/bundled dependencies retain their own licenses.

Automated runtime tests are headless. The maintainer tested the initial app
interactively, but future Wayland/X11/GPU behavior is not guaranteed. PIE,
ReleaseFast, tests, signatures and Claude review do not establish complete
hardening or freedom from vulnerabilities. Decide whether these tolerances suit
you; otherwise use a maintained distribution package you trust.
