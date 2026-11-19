# ghostty-debian

Independent personal **Ghostty 1.4.0** packaging for **Debian 13 (trixie), amd64**.
Package: `ghostty`, version `1.4.0-1personal1~deb13u1`. Not an official Ghostty
or Debian package, apt repository, or supported distribution service.

> **zervin's personal risk tolerance:** I maintain this for my own use and my own
> risk tolerance. My willingness to run these builds is not a recommendation
> that you trust them. Your requirements may be different; review the code,
> inputs, and build records yourself, or use a distribution package you trust.
> I promise neither security, timely updates, nor reproducible builds.

## Why another repository?

| Repository | Role |
| --- | --- |
| [ghostty-org/ghostty](https://github.com/ghostty-org/ghostty) | Upstream terminal emulator and signed source releases; authoritative application source. |
| [mkasberg/ghostty-ubuntu](https://github.com/mkasberg/ghostty-ubuntu) | Established unofficial Ubuntu/Debian packages, broader distro/architecture support, PPA and installer options; see its [README](https://github.com/mkasberg/ghostty-ubuntu/blob/main/README.md) and [workflows](https://github.com/mkasberg/ghostty-ubuntu/tree/main/.github/workflows). |
| [zervin/ghostty-debian](https://github.com/zervin/ghostty-debian) | Narrow personal trixie/amd64 build, reviewed stable inputs, manual dispatch, offline compilation, and manually reviewed draft releases. |

These are different maintenance and trust choices, not evidence that another
maintainer or upstream is malicious. This is an independent repository, not a
fork. Packaging and scripts here are original MIT-licensed work; no mkasberg
scripts were copied (no repository license was visible during initial review).
Upstream and bundled dependency licenses remain their own; see `debian/copyright`.

## Normal use: GitHub builds it

[Build runs](https://github.com/zervin/ghostty-debian/actions/workflows/release.yml) ·
[Upstream checks](https://github.com/zervin/ghostty-debian/actions/workflows/check-upstream.yml) ·
[Releases](https://github.com/zervin/ghostty-debian/releases)

1. A daily (08:23 UTC) or manual check finds new stable `vX.Y.Z` upstream tags.
2. It requires a GitHub-verified annotated tag and pins its commit/source URL in
   an update PR. Zig stays pinned; an incompatible minimum stops the check.
3. **You review and merge the PR.** GitHub then builds and tests the package.
4. Successful CI creates a **draft release** with the `.deb` and build records.
   Review it and test the GUI before choosing to publish.

There is no automatic merge or public publication. Tags may precede source
availability, and Zig/upstream build changes can require manual maintenance.
The updater never overwrites an existing automation branch. Allow GitHub Actions
PR creation in repository settings. Token-created PRs do not trigger other
workflows themselves; your human merge to `main` triggers the build.

Your laptop only needs to download and install the reviewed `.deb`; Docker and
compilers are **not** required for normal use. Local builds below are optional
staging/debugging, using the same scripts as hosted CI.

## Optional local build

Prerequisites: native Linux amd64, Docker with Buildx and a working daemon,
Git, Bash, Python 3, ShellCheck, disk space and RAM for a large Zig build.
Docker access is effectively host-root access. Use a disposable host/runner and
a clean checkout containing no credentials or personal files.

```sh
git clone https://github.com/zervin/ghostty-debian.git
cd ghostty-debian
bash tests/static.sh
bash scripts/build.sh
```

The build script creates an image from the digest in `release.conf`, downloads
and minisign-verifies the source and Zig, then runs `zig build --fetch=all` from
the verified source with fresh caches. Zig recursively checks the signed-source
manifests' dependency hashes and populates normal local `source/zig-pkg` storage
without executing build steps. Signed manifests and hashes are never rewritten.

With Zig 0.17.1, bare URL `zig fetch` can recompress an extra outer wrapper into
its global archive cache; consuming that archive later causes hash mismatches.
Preparation therefore does not use upstream's bare-fetch cache script or reuse
old archives. Normal compilation uses the correctly rooted `zig-pkg` directories;
there is no custom extractor, `--pkg-dir` override, or `--system` mode.
Only then does it compile with `--network none`, uid 1000, no capabilities,
read-only root/checkout, and writable scratch/output. No host home, Docker socket,
SSH agent, or token is mounted into these build containers. The host driver needs
the daemon; the compiler does not. Preparation has network access to fetch the
verified manifests' dependency URLs in that isolated container. There is no `--system` build mode or
downstream bzip/harfbuzz patch set.

The defaults are `.work/build` and `artifacts`; **both must initially be empty**.
Preserve previous records, then use new empty directories for another run:

```sh
WORK_DIR="$PWD/.work/second" OUTPUT_DIR="$PWD/artifacts-second" bash scripts/build.sh
```

Scratch is owned by container uid 1000 and may require privileged cleanup on a
host with another UID. Never point scratch/output at existing personal directories.

Build flags are `ReleaseSafe`, baseline CPU, PIE, Sentry disabled, bundled
GTK4 layer-shell, emitted docs, and a version derived from the Debian changelog.
`DEB_BUILD_MAINT_OPTIONS=hardening=+all` does **not** establish Zig hardening;
inspect the compiler output and ELF yourself. Debhelper generates shared-library
dependencies; no handwritten maintainer scripts or alternatives registration
are used. Layer-shell is private under `/usr/lib/ghostty`; the executable's only
RUNPATH is `$ORIGIN/../lib/ghostty`, never a build or working-directory path.
Development headers/static archives and the separate VT library are not shipped.
This pristine-source build retains upstream bundled libraries. Four exact lintian
`embedded-library` exceptions (FreeType, libpng, libxml2, zlib) are documented in
`debian/ghostty.lintian-overrides`. These copies do **not** receive Debian's library
security updates: rebuilding on upstream fixes is my responsibility. The package retains upstream desktop files,
icons, shell completions, terminfo, manuals, shell integrations and themes, plus
upstream and discovered dependency license/notice files.

## Manual GitHub build and draft review

Builds run on reviewed packaging changes pushed/merged to `main`, or manual
`workflow_dispatch` on `main`. There are no PR-code, nightly, or upstream-main
builds. Upstream detection is scheduled separately and only proposes a PR.
With GitHub CLI authenticated on your host:

```sh
gh workflow run release.yml --repo zervin/ghostty-debian --ref main
gh run list --repo zervin/ghostty-debian --workflow release.yml
```

The read-only build job receives no repository secrets. A separate clean runner
has release-write permission, downloads only data, never checks out or executes
artifacts, and creates a **draft** targeted at the workflow's exact commit.
It refuses an existing release tag. Changes to inputs require deliberate review
of config, changelog, rules, tests, and trust documentation before dispatch.

Before manually publishing the draft:

1. Review the workflow commit and logs, source/toolchain signature records,
   dependency-cache hashes, apt inventory, image IDs, `.buildinfo` and `.changes`.
2. Review `lintian.log`: errors fail the build; warnings are retained, **not**
   blanket-approved or suppressed. Investigate and document each warning in the
   draft notes. The initial local build had only two groff line-adjustment
   warnings in generated manuals after the four explicit bundling exceptions.
3. Verify `SHA256SUMS` and the exact package contents/dependencies.
4. Perform an interactive Wayland/X11 check. Automated tests are headless only;
   window creation, rendering, desktop integration and GPU behavior remain pending.
5. Edit the draft's notes with that review and known limitations; publish only if
   it meets your own risk tolerance.

`artifacts/` includes the `.deb`, `.buildinfo`, `.changes`, `SHA256SUMS`, verified
input hashes and detached minisign signatures, signature-verification logs,
global-cache and local-package file hashes, offline cache-regression results,
build metadata and apt inventory, image inspection, package contents/control,
lintian log, and preparation/build/smoke logs.
Large source/toolchain archives remain in scratch, not release assets. Checksums
computed after signature verification are records, **not independently anchored
source hashes**. Release checksums are not a separate maintainer signature.

## Install a reviewed release

Download the **exact** `.deb` and `SHA256SUMS` from a reviewed release, not a
random workflow artifact. In the download directory:

```sh
# If only the .deb was downloaded, verify its entry specifically:
grep '  ghostty_1.4.0-1personal1~deb13u1_amd64.deb$' SHA256SUMS | sha256sum --check --strict
sudo apt install ./ghostty_1.4.0-1personal1~deb13u1_amd64.deb
ghostty +version
# Optional removal:
sudo apt purge ghostty
```

Do not pipe downloaded scripts into a shell. `apt` resolves runtime dependencies;
there is no repository configured and no automatic update channel. This package
may conflict with other packages named `ghostty`; inspect existing installations
first. No other Debian release, Ubuntu release, or architecture is supported.

## Validation and limitations

Local staging passed source/toolchain signatures, offline dependency hash
regression, compilation, lintian (two manual-formatting warnings), clean Debian
installation, version/configuration/terminfo/resources checks, library resolution,
and purge. Hosted CI is the authoritative build for release assets; review its
successful run and exact commit rather than trusting local staging alone.

`bash tests/static.sh` checks shell syntax/ShellCheck, release identifiers and
injection rejection, fresh-cache fetch configuration, license collection including
`source/zig-pkg`, and selected packaging/workflow safety invariants. It does not
run Zig or substitute for a real build. Before offline compilation,
`tests/integration-cache.sh` checks the known libxev package's root and recomputes
its exact signed-manifest hash using local `zig fetch` in a separate fresh cache.
Run it manually in the prepared offline container with
`bash /repo/tests/integration-cache.sh /work/source`. It fails on a hash mismatch;
it is a sentinel regression, not an independent rehash of every dependency.
The build fails on lintian
errors and then installs the package with apt into a fresh pinned trixie base,
checks version, valid/invalid configuration, terminfo, resources, dynamic library
resolution and removal of the private layer-shell library. It does not launch a GUI.

GitHub, Docker/base images, Debian maintainers and moving signed apt repositories,
Ghostty, Zig and their compilers, transitive dependencies, signing-key custody,
and the maintainer's account all remain trusted. A digest-pinned base does not
freeze apt packages. There is no bit-reproducibility claim or security SLA.
See [SECURITY.md](SECURITY.md) for bootstrap provenance and threat boundaries.
