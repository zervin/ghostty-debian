# Security and trust

This is personal, best-effort packaging, not a security-maintained distribution.
Only the pinned Debian 13 amd64 configuration is intended for testing; no
supported-version or response-time promise is made. For sensitive reports use
GitHub private vulnerability reporting if enabled, or contact zervin through the
[GitHub profile](https://github.com/zervin). Do not post exploit details or
credentials in a public issue. Application vulnerabilities belong with
[Ghostty upstream](https://github.com/ghostty-org/ghostty/security/policy).

## Initial trust bootstrap (2026-11-07)

The following were read independently from official HTTPS documentation, not
inferred solely from this repository's supplied configuration:

* Ghostty's [build documentation](https://ghostty.org/docs/install/build) publishes
  `RWQlAjJC23149WL2sEpT/l0QKy7hMIFhYdQOFy0Z7z7PbneUgvlsnYcV`.
* Zig's [download page](https://ziglang.org/download/) publishes
  `RWSGOq2NVecA2UPNdBUZykf1CCb147pkmdtYxgb3Ti+JO/wCYvhbAb/U` and lists Zig 0.17.1.
* Source URL: `https://release.files.ghostty.org/1.4.0/ghostty-1.4.0.tar.gz`;
  detached signature is the same URL plus `.minisig`.
* Toolchain URL: `https://ziglang.org/download/0.17.1/zig-x86_64-linux-0.17.1.tar.xz`;
  detached signature is the same URL plus `.minisig`.
* The reviewed [Ghostty tag commit](https://github.com/ghostty-org/ghostty/tree/83fb95624b0439ee660c2679b43b38c8b63769cd)
  is `83fb95624b0439ee660c2679b43b38c8b63769cd`. Its
  [build.zig.zon](https://github.com/ghostty-org/ghostty/blob/83fb95624b0439ee660c2679b43b38c8b63769cd/build.zig.zon)
  requires Zig 0.17.0 minimum. The documentation's version table was stale;
  the selected stable toolchain is 0.17.1. An actual build is still needed to
  demonstrate compatibility.
* Build option names were checked in
  [Config.zig](https://github.com/ghostty-org/ghostty/blob/83fb95624b0439ee660c2679b43b38c8b63769cd/src/build/Config.zig)
  and Zig's standard target/optimization options. Zig 0.17.1's
  [Optimize.fromString](https://codeberg.org/ziglang/zig/src/tag/0.17.1/lib/std/lang.zig)
  still accepts `ReleaseSafe` as a deprecated alias for `safe`; its
  [Maker](https://codeberg.org/ziglang/zig/src/tag/0.17.1/lib/compiler/Maker.zig)
  supports `DESTDIR` for Debian staging. The bundled layer-shell
  dynamic library installation is visible in
  [SharedDeps.zig](https://github.com/ghostty-org/ghostty/blob/83fb95624b0439ee660c2679b43b38c8b63769cd/src/build/SharedDeps.zig).
* `docker buildx imagetools inspect debian:trixie-slim` resolved index digest
  `sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2`
  and linux/amd64 manifest digest
  `sha256:7378260c0a098d27ac206225db5e7d92b8c7c84ea7afccc86eeb513756bbd392`.
  The latter is pinned in `release.conf` and `Dockerfile`.

HTTPS documentation is a trust-on-first-review bootstrap, not an independent
cryptographic certification of the keys. Re-check keys through official channels
before changes; never silently accept a new key after verification fails.
The Git commit is review provenance, **not a claim that the signed distribution
tarball is byte-identical to a GitHub archive**. The release signer authenticates
the tarball and the tarball's dependency-fetch script/list. No independently
anchored source/toolchain SHA256 was supplied initially: preparation verifies
minisign first, then records the observed hashes and signature records. These
hashes can be reviewed and pinned in a later deliberate update.

## Remaining trust and isolation

* Signatures authenticate holders of the configured signing keys, not code
  correctness or freedom from vulnerabilities. GitHub/TLS/account compromises,
  malicious or compromised compilers, and compromised upstreams remain possible.
* Dependency downloads follow the verified upstream fetch script and Zig package
  hashes. They are transitive supply-chain inputs, not a separate maintainer audit.
  License/notice collection is heuristic; inspect license coverage before
  redistribution. The packaging MIT license does not relicense bundled code/fonts.
* Debian apt verifies its signed repository metadata but repositories move.
  Base-image digest, inventories and `.buildinfo` aid review, not reproducibility.
  This is not a Debian-policy-complete source archive or Debian official upload;
  only a binary build is produced and it can contain bundled dependencies.
* Online preparation and offline compilation are separate containers. Both use
  uid 1000, dropped capabilities, no-new-privileges, a read-only root/checkout,
  and isolated writable scratch. No credentials, home, agent or daemon socket are
  mounted. The preparation container can access the network and fetched code;
  the compilation container uses `--network none`. Kernel/container escapes,
  resource exhaustion and vulnerabilities in the host Docker daemon are outside
  this boundary; a disposable runner is recommended.
* The fresh installation test is root inside a disposable base container and has
  apt network access. A `.deb` is executable privileged installation content;
  generated debhelper scripts/triggers are still code. Review them before use.
  No handwritten maintainer scripts are supplied. ldconfig registration/removal
  of bundled GTK4 layer-shell is explicitly checked.
* Workflow actions are full-SHA pinned, checkout credentials are not persisted,
  the build job is read-only, and a separate clean publish runner alone receives
  release-write permission. Downloaded artifacts are uploaded as data, not
  executed. Manual dispatch is restricted to `main`; no automatic updates or
  privileged pull-request builds exist. Maintainers with write access can still
  alter this policy and GitHub controls the runners/token service.
* `SHA256SUMS` detects differing files relative to the downloaded checksum list;
  it does not independently authenticate an uploader when both are compromised.
  No signed `.deb`, signed `.changes`, SLSA attestation, or security guarantee is
  claimed. Review draft release notes and exact target commit before publication.
* Headless tests do not prove interactive GUI/Wayland/X11/GPU operation.
  Lintian warnings require manual review, and PIE/ReleaseSafe do not establish
  complete hardening. Timely updates and uninterrupted availability are not
  guaranteed; decide for yourself whether these tradeoffs are acceptable.
