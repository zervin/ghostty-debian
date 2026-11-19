import base64
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_upstream", ROOT / "scripts/check-upstream.py")
upstream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upstream)

COMMIT = "a" * 40
TAG_SHA = "b" * 40
CONFIG = """# Preserve reviewed compiler and keys.
GHOSTTY_VERSION=1.4.0
GHOSTTY_COMMIT=cccccccccccccccccccccccccccccccccccccccc
DEBIAN_VERSION=1.4.0-2personal3~deb13u1
ZIG_VERSION=0.17.1
GHOSTTY_URL=https://release.files.ghostty.org/1.4.0/ghostty-1.4.0.tar.gz
ZIG_URL=https://ziglang.org/download/0.17.1/zig-x86_64-linux-0.17.1.tar.xz
GHOSTTY_KEY=keep-source-key
ZIG_KEY=keep-zig-key
"""
CHANGELOG = """ghostty (1.4.0-2personal3~deb13u1) trixie; urgency=medium

  * Existing entry.

 -- zervin <zervin@users.noreply.github.com>  Sat, 07 Nov 2026 00:00:00 +0000
"""


def fixture(minimum="0.17.1"):
    responses = {
        f"{upstream.UPSTREAM}/tags?per_page=100&page=1": [
            {"name": name, "commit": {"sha": COMMIT}}
            for name in ["v1.4.0", "v1.5.0", "v1.10.0-rc1", "vt-2026-10-01", "tip",
                         "v01.99.0", "v9.0.0+metadata", "v1.5.1-pre", "v2.0"]
        ],
        f"{upstream.UPSTREAM}/git/ref/tags/v1.5.0": {
            "ref": "refs/tags/v1.5.0", "object": {"type": "tag", "sha": TAG_SHA}},
        f"{upstream.UPSTREAM}/git/tags/{TAG_SHA}": {
            "sha": TAG_SHA, "tag": "v1.5.0", "object": {"type": "commit", "sha": COMMIT},
            "verification": {"verified": True, "reason": "valid"}},
        f"{upstream.UPSTREAM}/contents/build.zig.zon?ref={COMMIT}": {
            "encoding": "base64", "type": "file",
            "content": base64.b64encode(
                f'.{{\n    .minimum_zig_version = "{minimum}",\n}}\n'.encode()).decode()},
    }
    return responses, Mock(side_effect=responses.__getitem__)


class CheckUpstreamTests(unittest.TestCase):
    def setUp(self):
        self.config = upstream.read_config(CONFIG)
        self.responses, self.api = fixture()

    def test_selects_only_stable_semver_and_pins_verified_commit(self):
        candidate = upstream.discover(self.config, self.api)
        self.assertTrue(candidate["update_available"])
        self.assertEqual(candidate["version"], "1.5.0")
        self.assertEqual(candidate["commit"], COMMIT)
        self.assertEqual(candidate["minimum_zig_version"], "0.17.1")
        self.assertEqual(candidate["zig_version"], "0.17.1")
        self.assertEqual(candidate["debian_version"], "1.5.0-1personal1~deb13u1")
        self.assertEqual(candidate["url"], "https://release.files.ghostty.org/1.5.0/ghostty-1.5.0.tar.gz")
        self.assertFalse(any("releases/latest" in call.args[0] for call in self.api.call_args_list))

    def test_paginates_and_orders_versions_numerically(self):
        path = f"{upstream.UPSTREAM}/tags?per_page=100&page="
        self.responses[path + "1"] = [{"name": f"vt-{i}"} for i in range(100)]
        self.responses[path + "2"] = [{"name": "v1.9.0"}, {"name": "v1.10.0"}]
        self.config["GHOSTTY_VERSION"] = "1.10.0"
        self.assertEqual(upstream.discover(self.config, self.api),
                         {"update_available": False, "version": "1.10.0"})
        self.assertEqual(self.api.call_count, 2)

    def test_no_update_does_not_require_tag_verification(self):
        self.config["GHOSTTY_VERSION"] = "1.5.0"
        self.assertFalse(upstream.discover(self.config, self.api)["update_available"])
        self.assertEqual(self.api.call_count, 1)

    def test_rejects_no_stable_tags(self):
        self.responses[f"{upstream.UPSTREAM}/tags?per_page=100&page=1"] = [{"name": "tip"}]
        with self.assertRaisesRegex(ValueError, "No stable"):
            upstream.discover(self.config, self.api)

    def test_requires_annotated_tag(self):
        self.responses[f"{upstream.UPSTREAM}/git/ref/tags/v1.5.0"]["object"]["type"] = "commit"
        with self.assertRaisesRegex(ValueError, "annotated"):
            upstream.discover(self.config, self.api)

    def test_rejects_unsigned_or_invalid_verification(self):
        for verification in [{}, {"verified": False, "reason": "unsigned"},
                             {"verified": True, "reason": "expired_key"},
                             {"verified": "true", "reason": "valid"}]:
            with self.subTest(verification=verification):
                self.responses[f"{upstream.UPSTREAM}/git/tags/{TAG_SHA}"]["verification"] = verification
                with self.assertRaisesRegex(ValueError, "signature verification"):
                    upstream.discover(self.config, self.api)

    def test_rejects_tag_commit_name_and_object_mismatch(self):
        for change in [{"object": {"type": "commit", "sha": "d" * 40}},
                       {"object": {"type": "tag", "sha": COMMIT}},
                       {"tag": "v1.5.1"}, {"sha": "d" * 40}]:
            with self.subTest(change=change):
                responses, api = fixture()
                responses[f"{upstream.UPSTREAM}/git/tags/{TAG_SHA}"].update(change)
                with self.assertRaisesRegex(ValueError, "mismatch"):
                    upstream.discover(self.config, api)

    def test_rejects_incompatible_zig_without_upgrading(self):
        for minimum in ["0.18.0", "0.18.0-dev.1"]:
            with self.subTest(minimum=minimum):
                _, api = fixture(minimum)
                with self.assertRaises(ValueError):
                    upstream.discover(self.config, api)
                self.assertEqual(self.config["ZIG_VERSION"], "0.17.1")

    def test_accepts_newer_pinned_zig_than_minimum(self):
        _, api = fixture("0.16.0")
        self.assertEqual(upstream.discover(self.config, api)["zig_version"], "0.17.1")

    def test_rejects_unreadable_or_missing_minimum_zig(self):
        contents = self.responses[f"{upstream.UPSTREAM}/contents/build.zig.zon?ref={COMMIT}"]
        for source in ['.{}', '.{\n.minimum_zig_version = "0.17.1",\n.minimum_zig_version = "0.18.0",\n}']:
            contents["content"] = base64.b64encode(source.encode()).decode()
            with self.assertRaisesRegex(ValueError, "unique upstream minimum"):
                upstream.discover(self.config, self.api)

    def test_strict_semver(self):
        for version in ["1.2", "01.2.3", "1.02.3", "1.2.03", "1.2.3-rc1", "1.2.3+build", "tip", "1.2.3\n"]:
            with self.subTest(version=version), self.assertRaises(ValueError):
                upstream.version_tuple(version)

    def test_config_rejects_duplicates_and_mismatch(self):
        for text in [CONFIG + "ZIG_VERSION=0.18.0\n", CONFIG.replace("DEBIAN_VERSION=1.4.0", "DEBIAN_VERSION=1.3.0"),
                     CONFIG.replace("GHOSTTY_COMMIT=" + "c" * 40, "GHOSTTY_COMMIT=bad")]:
            with self.assertRaises(ValueError):
                upstream.read_config(text)

    def test_trust_guard_rejects_pr_and_non_main_actions(self):
        for event, ref in [("pull_request", "refs/heads/main"), ("pull_request_target", "refs/heads/main"),
                           ("push", "refs/heads/main"), ("workflow_dispatch", "refs/heads/other")]:
            with self.subTest(event=event, ref=ref), self.assertRaises(ValueError):
                upstream.trust_guard({"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": event, "GITHUB_REF": ref})
        for event in ["schedule", "workflow_dispatch"]:
            upstream.trust_guard({"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": event, "GITHUB_REF": "refs/heads/main"})
        upstream.trust_guard({})

    def make_root(self, root):
        (root / "debian").mkdir()
        (root / "release.conf").write_text(CONFIG)
        (root / "debian/changelog").write_text(CHANGELOG)

    def test_update_only_config_and_changelog_preserving_compiler_and_maintainer(self):
        candidate = upstream.discover(self.config, self.api)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_root(root)
            upstream.update_files(root, candidate)
            updated = upstream.read_config((root / "release.conf").read_text())
            for key in self.config:
                if key not in {"GHOSTTY_VERSION", "GHOSTTY_COMMIT", "DEBIAN_VERSION", "GHOSTTY_URL"}:
                    self.assertEqual(updated[key], self.config[key])
            self.assertEqual(updated["GHOSTTY_COMMIT"], COMMIT)
            changelog = (root / "debian/changelog").read_text()
            self.assertTrue(changelog.startswith("ghostty (1.5.0-1personal1~deb13u1) trixie; urgency=medium\n"))
            self.assertIn(" -- zervin <zervin@users.noreply.github.com>  ", changelog)
            self.assertTrue(changelog.endswith(CHANGELOG))
            self.assertEqual(sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()),
                             ["debian/changelog", "release.conf"])

    def test_check_mode_emits_metadata_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_root(root)
            output = io.StringIO()
            with patch.object(upstream, "__file__", str(root / "scripts/check-upstream.py")), \
                    patch.object(upstream, "github_api", self.api), \
                    patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), \
                    patch("sys.argv", ["check-upstream.py", "--check"]), redirect_stdout(output):
                upstream.main()
            self.assertEqual(json.loads(output.getvalue())["commit"], COMMIT)
            self.assertEqual((root / "release.conf").read_text(), CONFIG)
            self.assertEqual((root / "debian/changelog").read_text(), CHANGELOG)

    def test_update_mode_writes_review_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_root(root)
            output = io.StringIO()
            with patch.object(upstream, "__file__", str(root / "scripts/check-upstream.py")), \
                    patch.object(upstream, "github_api", self.api), \
                    patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), \
                    patch("sys.argv", ["check-upstream.py", "--update", "--expected-version", "1.5.0"]), \
                    redirect_stdout(output):
                upstream.main()
            self.assertEqual(json.loads(output.getvalue())["version"], "1.5.0")
            self.assertEqual(upstream.read_config((root / "release.conf").read_text())["GHOSTTY_VERSION"], "1.5.0")
            self.assertTrue((root / "debian/changelog").read_text().endswith(CHANGELOG))

    def test_incompatible_zig_update_does_not_write(self):
        _, api = fixture("0.18.0")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_root(root)
            with patch.object(upstream, "__file__", str(root / "scripts/check-upstream.py")), \
                    patch.object(upstream, "github_api", api), \
                    patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), \
                    patch("sys.argv", ["check-upstream.py", "--update"]):
                with self.assertRaisesRegex(ValueError, "Review compiler inputs manually"):
                    upstream.main()
            self.assertEqual((root / "release.conf").read_text(), CONFIG)
            self.assertEqual((root / "debian/changelog").read_text(), CHANGELOG)

    def test_update_expected_version_mismatch_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_root(root)
            with patch.object(upstream, "__file__", str(root / "scripts/check-upstream.py")), \
                    patch.object(upstream, "github_api", self.api), \
                    patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), \
                    patch("sys.argv", ["check-upstream.py", "--update", "--expected-version", "1.6.0"]):
                with self.assertRaisesRegex(ValueError, "candidate changed"):
                    upstream.main()
            self.assertEqual((root / "release.conf").read_text(), CONFIG)
            self.assertEqual((root / "debian/changelog").read_text(), CHANGELOG)


class CheckUpstreamWorkflowTests(unittest.TestCase):
    def test_workflow_trust_permissions_and_collision_safety(self):
        text = (ROOT / ".github/workflows/check-upstream.yml").read_text()
        self.assertIn("schedule:", text)
        self.assertIn("workflow_dispatch:", text)
        for trigger in ["pull_request", "pull_request_target", "push"]:
            self.assertNotRegex(text, r"(?m)^  " + trigger + ":")
        check, propose = text.split("  propose:", 1)
        self.assertNotIn("contents: write", check)
        self.assertNotIn("pull-requests: write", check)
        self.assertIn("contents: write", propose)
        self.assertIn("pull-requests: write", propose)
        self.assertEqual(text.count("persist-credentials: false"), 2)
        self.assertEqual(text.count("uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262"), 2)
        self.assertEqual(text.count("github.ref == 'refs/heads/main'"), 2)
        self.assertIn('BRANCH="automation/ghostty-$VERSION"', propose)
        self.assertIn('if [[ -n $existing ]]; then', propose)
        self.assertNotIn("--force", text)
        self.assertIn('git push origin "HEAD:refs/heads/$BRANCH"', propose)
        self.assertIn('git add -- release.conf debian/changelog', propose)
        self.assertIn('gh pr create', propose)
        self.assertNotIn("gh pr merge", text)
        self.assertNotIn("gh release", text)
        self.assertNotIn("${{", text.split("run: |", 1)[1].split("  propose:", 1)[0])


if __name__ == "__main__":
    unittest.main()
