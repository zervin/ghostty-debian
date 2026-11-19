import base64
from contextlib import redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("update_gate", ROOT / "scripts/update-gate.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

BASE = "1" * 40
HEAD = "2" * 40
UPSTREAM_BASE = "3" * 40
UPSTREAM_HEAD = "4" * 40
BASE_TREE = "5" * 40
HEAD_TREE = "6" * 40
TAG = "7" * 40
REPO = "owner/packaging"
PREFIX = "repos/" + REPO
PR_PATH = PREFIX + "/pulls/42"
COMPARE = f"{gate.check_upstream.UPSTREAM}/compare/{UPSTREAM_BASE}...{UPSTREAM_HEAD}"
CONFIG = f"""# Preserve all trusted inputs and formatting.
GHOSTTY_VERSION=1.4.0
GHOSTTY_COMMIT={UPSTREAM_BASE}
DEBIAN_VERSION=1.4.0-1personal2.deb13u1
ZIG_VERSION=0.17.1
GHOSTTY_URL=https://release.files.ghostty.org/1.4.0/ghostty-1.4.0.tar.gz
GHOSTTY_KEY=trusted-source-key
ZIG_URL=https://ziglang.org/download/0.17.1/zig-x86_64-linux-0.17.1.tar.xz
ZIG_KEY=trusted-compiler-key
DEBIAN_IMAGE=debian:trixie-slim@sha256:trusted-digest
"""
CHANGELOG = """ghostty (1.4.0-1personal2.deb13u1) trixie; urgency=medium

  * Existing reviewed entry.

 -- Maintainer Name <maintainer@example.org>  Sat, 07 Nov 2026 00:00:00 +0000
"""
ASSESSMENT = {"head_sha": HEAD, "decision": "approve", "complete": True,
              "high_critical_findings": [], "blocking_findings": [], "summary": "Complete review; no blockers."}
PATCH = "@@ -1 +1 @@\n-old\n+new"
DIFF = "diff --git a/src/main.zig b/src/main.zig\nindex 1111111..2222222 100644\n--- a/src/main.zig\n+++ b/src/main.zig\n" + PATCH + "\n"


def blob(text):
    data = text.encode()
    sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    return sha, {"sha": sha, "encoding": "base64", "size": len(data),
                 "content": base64.b64encode(data).decode()}


def fixtures():
    upstream = gate.check_upstream.UPSTREAM
    responses = {
        upstream + "/tags?per_page=100&page=1": [{"name": "v1.5.0", "commit": {"sha": UPSTREAM_HEAD}}],
        upstream + "/git/ref/tags/v1.5.0": {"ref": "refs/tags/v1.5.0", "object": {"type": "tag", "sha": TAG}},
        upstream + f"/git/tags/{TAG}": {"sha": TAG, "tag": "v1.5.0", "object": {"type": "commit", "sha": UPSTREAM_HEAD},
                                      "verification": {"verified": True, "reason": "valid"}},
        upstream + f"/contents/build.zig.zon?ref={UPSTREAM_HEAD}": {
            "encoding": "base64", "type": "file", "content": base64.b64encode(
                b'.{\n.minimum_zig_version = "0.17.1",\n}').decode()},
    }
    candidate = gate.check_upstream.discover(gate.check_upstream.read_config(CONFIG), responses.__getitem__)
    # Generate the accepted shape with the real proposer, not a duplicate implementation.
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "debian").mkdir()
        (root / "release.conf").write_text(CONFIG)
        (root / "debian/changelog").write_text(CHANGELOG)
        gate.check_upstream.update_files(root, candidate)
        head_config = (root / "release.conf").read_text()
        head_changelog = (root / "debian/changelog").read_text()
    remote = {"id": 123, "full_name": REPO, "fork": False}
    responses[PR_PATH] = {"number": 42, "state": "open", "draft": False, "commits": 1,
                          "user": {"login": "github-actions[bot]", "type": "Bot"},
                          "base": {"sha": BASE, "ref": "main", "repo": copy.deepcopy(remote)},
                          "head": {"sha": HEAD, "ref": "automation/ghostty-1.5.0", "repo": copy.deepcopy(remote)}}
    responses[PREFIX + "/git/ref/heads/main"] = {"object": {"sha": BASE}}
    responses[PR_PATH + "/commits?per_page=100&page=1"] = [{"sha": HEAD}]
    for commit, tree, config, changelog in [(BASE, BASE_TREE, CONFIG, CHANGELOG),
                                          (HEAD, HEAD_TREE, head_config, head_changelog)]:
        responses[PREFIX + f"/git/commits/{commit}"] = {
            "sha": commit, "tree": {"sha": tree}, "parents": [{"sha": BASE}] if commit == HEAD else []}
        entries = []
        for name, text in [("release.conf", config), ("debian/changelog", changelog)]:
            sha, data = blob(text)
            responses[PREFIX + f"/git/blobs/{sha}"] = data
            entries.append({"path": name, "mode": "100644", "type": "blob", "sha": sha})
        responses[PREFIX + f"/git/trees/{tree}?recursive=1"] = {"sha": tree, "truncated": False, "tree": entries}
    responses[PR_PATH + "/files?per_page=100&page=1"] = [
        {"filename": f["path"], "status": "modified", "sha": f["sha"]}
        for f in responses[PREFIX + f"/git/trees/{HEAD_TREE}?recursive=1"]["tree"]]
    responses[COMPARE + "?per_page=100&page=1"] = {
        "status": "ahead", "base_commit": {"sha": UPSTREAM_BASE}, "merge_base_commit": {"sha": UPSTREAM_BASE},
        "total_commits": 1, "ahead_by": 1, "behind_by": 0, "commits": [{"sha": UPSTREAM_HEAD}],
        "files": [{"filename": "src/main.zig", "status": "modified", "additions": 1,
                   "deletions": 1, "changes": 2, "patch": PATCH}]}
    responses[COMPARE] = DIFF
    return responses


class UpdateGateValidateTests(unittest.TestCase):
    def setUp(self):
        self.responses = fixtures()
        self.api = Mock(side_effect=lambda path, **kwargs: copy.deepcopy(self.responses[path]))
        self.environment = patch.dict(os.environ, {"GITHUB_REPOSITORY": REPO, "GITHUB_ACTIONS": "false"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name)

    def validate(self, metadata_only=False):
        return gate.validate(42, self.output, metadata_only, self.api)

    def head_entry(self, name):
        return next(f for f in self.responses[PREFIX + f"/git/trees/{HEAD_TREE}?recursive=1"]["tree"] if f["path"] == name)

    def change_text(self, name, transform):
        entry = self.head_entry(name)
        data = self.responses[PREFIX + f"/git/blobs/{entry['sha']}"]
        text = base64.b64decode(data["content"]).decode()
        sha, data = blob(transform(text))
        self.responses[PREFIX + f"/git/blobs/{sha}"] = data
        entry["sha"] = sha
        for file in self.responses[PR_PATH + "/files?per_page=100&page=1"]:
            if file["filename"] == name:
                file["sha"] = sha

    def test_accepts_real_proposer_shape_and_writes_bounded_exact_source_context(self):
        result = self.validate()
        self.assertEqual(result, {"head_sha": HEAD, "base_sha": BASE, "version": "1.5.0",
                                  "package_version": "1.5.0-1personal1.deb13u1", "pr_number": "42",
                                  "upstream_base": UPSTREAM_BASE, "upstream_head": UPSTREAM_HEAD})
        context = json.loads((self.output / "review-context.json").read_text())
        self.assertTrue(context["review_complete"])
        self.assertIn("UNTRUSTED SOURCE DATA", context["warning"])
        self.assertEqual(context["upstream_diff"], DIFF)
        self.assertEqual((self.output / "upstream.diff").read_bytes(), DIFF.encode())
        self.assertLessEqual((self.output / "review-context.json").stat().st_size, 250 * 1024)

    def test_metadata_only_revalidates_without_source_context_and_removes_old_diff(self):
        self.validate()
        self.api.reset_mock()
        self.validate(metadata_only=True)
        self.assertFalse((self.output / "upstream.diff").exists())
        context = json.loads((self.output / "review-context.json").read_text())
        self.assertFalse(context["review_complete"])
        self.assertIsNone(context["upstream_diff"])
        self.assertFalse(any(COMPARE in call.args[0] for call in self.api.call_args_list))
        self.assertTrue(any("/git/tags/" in call.args[0] for call in self.api.call_args_list))

    def test_rejects_untrusted_pr_identity_branch_and_state(self):
        variations = [(("state",), "closed"), (("draft",), True), (("user", "login"), "attacker"),
                      (("user", "type"), "User"), (("number",), 41), (("commits",), 2),
                      (("base", "ref"), "other"), (("base", "sha"), "8" * 40),
                      (("head", "sha"), "bad"), (("head", "repo", "fork"), True),
                      (("head", "repo", "full_name"), "attacker/packaging"),
                      (("head", "repo", "id"), 999), (("base", "repo", "fork"), True)]
        for branch in ["automation/ghostty-1.5.0-rc1", "automation/ghostty-01.5.0", "automation/ghostty-1.5.0\n",
                       "automation/ghostty-1.4.0", "automation/ghostty-1.6.0", "evil"]:
            variations.append((("head", "ref"), branch))
        for keys, value in variations:
            with self.subTest(keys=keys, value=value):
                self.responses = fixtures()
                target = self.responses[PR_PATH]
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value
                with self.assertRaises(ValueError):
                    self.validate()

    def test_rejects_extra_commit_stale_parent_and_merge_commit(self):
        for parents in [[], [{"sha": "9" * 40}], [{"sha": BASE}, {"sha": "9" * 40}]]:
            with self.subTest(parents=parents):
                self.responses[PREFIX + f"/git/commits/{HEAD}"]["parents"] = parents
                with self.assertRaisesRegex(ValueError, "sole parent"):
                    self.validate()
        self.responses = fixtures()
        self.responses[PR_PATH + "/commits?per_page=100&page=1"].append({"sha": "9" * 40})
        with self.assertRaisesRegex(ValueError, "commit list"):
            self.validate()

    def test_rejects_hidden_extra_file_modes_symlinks_and_incomplete_trees(self):
        for mutation in ["extra", "mode", "symlink", "truncated", "files"]:
            with self.subTest(mutation=mutation):
                self.responses = fixtures()
                tree = self.responses[PREFIX + f"/git/trees/{HEAD_TREE}?recursive=1"]
                if mutation == "extra":
                    tree["tree"].append({"path": "scripts/evil.sh", "mode": "100755", "type": "blob", "sha": "9" * 40})
                elif mutation == "mode":
                    self.head_entry("release.conf")["mode"] = "100755"
                elif mutation == "symlink":
                    self.head_entry("debian/changelog")["mode"] = "120000"
                elif mutation == "truncated":
                    tree["truncated"] = True
                else:
                    self.responses[PR_PATH + "/files?per_page=100&page=1"][0]["status"] = "renamed"
                with self.assertRaises(ValueError):
                    self.validate()

    def test_rejects_compiler_key_image_shell_and_formatting_configuration_changes(self):
        for transform in [lambda s: s.replace("ZIG_VERSION=0.17.1", "ZIG_VERSION=0.18.0"),
                          lambda s: s.replace("trusted-source-key", "evil-key"),
                          lambda s: s.replace("trusted-digest", "evil-digest"),
                          lambda s: s + "EVIL=$(curl-attacker)\n",
                          lambda s: s.replace("# Preserve", "# Execute"),
                          lambda s: s.replace("GHOSTTY_COMMIT=" + UPSTREAM_HEAD, "GHOSTTY_COMMIT=" + "9" * 40),
                          lambda s: s.replace("ghostty-1.5.0.tar.gz", "evil.tar.gz"),
                          lambda s: s + "GHOSTTY_VERSION=1.5.0\n"]:
            with self.subTest(transform=transform):
                self.responses = fixtures()
                self.change_text("release.conf", transform)
                with self.assertRaises(ValueError):
                    self.validate()

    def test_rejects_arbitrary_changelog_commands_maintainer_date_and_old_entry_changes(self):
        for transform in [lambda s: s.replace("Independent personal package", "Run $(malicious)"),
                          lambda s: s.replace("Maintainer Name", "Attacker", 1),
                          lambda s: s + "\nextra entry\n",
                          lambda s: s.replace("Existing reviewed entry", "Mutated history"),
                          lambda s: s.replace("+0000", "+0100", 1),
                          lambda s: redate(s, "Fri, 99 Nov 2026 00:00:00 +0000"),
                          lambda s: redate(s, "Sat, 07 Nov 2026 00:00:00 +0000\n  * commands")]:
            with self.subTest(transform=transform):
                self.responses = fixtures()
                self.change_text("debian/changelog", transform)
                with self.assertRaises(ValueError):
                    self.validate()

    def test_requires_verified_current_upstream_tag_and_compatible_compiler(self):
        upstream = gate.check_upstream.UPSTREAM
        for mutation in ["unsigned", "wrong_commit", "compiler", "unavailable", "newer"]:
            with self.subTest(mutation=mutation):
                self.responses = fixtures()
                if mutation == "unsigned":
                    self.responses[upstream + f"/git/tags/{TAG}"]["verification"]["verified"] = False
                elif mutation == "wrong_commit":
                    self.responses[upstream + f"/git/tags/{TAG}"]["object"]["sha"] = "9" * 40
                elif mutation == "compiler":
                    self.responses[upstream + f"/contents/build.zig.zon?ref={UPSTREAM_HEAD}"]["content"] = base64.b64encode(
                        b'.{\n.minimum_zig_version = "0.18.0",\n}').decode()
                elif mutation == "unavailable":
                    self.responses[upstream + "/tags?per_page=100&page=1"] = []
                else:
                    self.responses[upstream + "/tags?per_page=100&page=1"][0]["name"] = "v1.6.0"
                with self.assertRaises((ValueError, KeyError)):
                    self.validate(metadata_only=True)

    def test_rejects_blob_decode_errors_wrong_size_and_oversize(self):
        for mutation in [{"content": "!!!"}, {"size": 0}, {"size": gate.MAX_TEXT_BYTES + 1}, {"encoding": "utf-8"}]:
            with self.subTest(mutation=mutation):
                self.responses = fixtures()
                data = self.responses[PREFIX + "/git/blobs/" + self.head_entry("release.conf")["sha"]]
                data.update(mutation)
                with self.assertRaises(ValueError):
                    self.validate()

    def test_rejects_comparison_limits_missing_binary_or_truncated_patches(self):
        for mutation in ["commits", "files", "patch", "binary_docs", "truncated", "stats", "raw", "raw_size", "ancestor"]:
            with self.subTest(mutation=mutation):
                self.responses = fixtures()
                compare = self.responses[COMPARE + "?per_page=100&page=1"]
                if mutation == "commits":
                    compare["total_commits"] = compare["ahead_by"] = 251
                elif mutation == "files":
                    compare["files"] *= 300
                elif mutation in {"patch", "binary_docs"}:
                    compare["files"][0].pop("patch")
                    if mutation == "binary_docs":
                        compare["files"][0]["filename"] = "docs/font.ttf"
                elif mutation == "truncated":
                    compare["files"][0]["patch"] = "@@ -1,2 +1,2 @@\n-old\n+new"
                elif mutation == "stats":
                    compare["files"][0]["additions"] = 2
                elif mutation == "raw":
                    self.responses[COMPARE] = DIFF.replace("+new", "+truncated")
                elif mutation == "raw_size":
                    self.responses[COMPARE] = "x" * (gate.MAX_DIFF_BYTES + 1)
                else:
                    compare["merge_base_commit"]["sha"] = "9" * 40
                with self.assertRaises(ValueError):
                    self.validate()

    def test_comparison_paginates_up_to_250_commits_without_silent_truncation(self):
        compare = self.responses[COMPARE + "?per_page=100&page=1"]
        commits = [{"sha": f"{i:040x}"} for i in range(1, 101)] + [{"sha": UPSTREAM_HEAD}]
        compare.update(total_commits=101, ahead_by=101, commits=commits[:100])
        self.responses[COMPARE + "?per_page=100&page=2"] = {"total_commits": 101, "commits": commits[100:]}
        self.validate()
        context = json.loads((self.output / "review-context.json").read_text())
        self.assertEqual(len(context["comparison"]["commits"]), 101)
        self.responses[COMPARE + "?per_page=100&page=2"]["commits"] = []
        with self.assertRaisesRegex(ValueError, "pagination"):
            self.validate()

    def test_serialized_full_reviewer_evidence_is_capped_at_250_kib(self):
        self.responses[COMPARE + "?per_page=100&page=1"]["commits"][0]["message"] = "x" * (250 * 1024)
        with self.assertRaisesRegex(ValueError, "250 KiB"):
            self.validate()
        self.assertFalse((self.output / "review-context.json").exists())

    def test_mutable_main_or_head_change_during_validation_blocks(self):
        for side in ["main", "head", "closed"]:
            with self.subTest(side=side):
                self.responses = fixtures()
                counts = {}
                def changing(path, **kwargs):
                    counts[path] = counts.get(path, 0) + 1
                    value = copy.deepcopy(self.responses[path])
                    if side == "main" and path == PREFIX + "/git/ref/heads/main" and counts[path] > 1:
                        value["object"]["sha"] = "9" * 40
                    if path == PR_PATH and counts[path] > 1:
                        if side == "head":
                            value["head"]["sha"] = "9" * 40
                        elif side == "closed":
                            value["state"] = "closed"
                    return value
                with self.assertRaises(ValueError):
                    gate.validate(42, self.output, api=Mock(side_effect=changing))

    def test_failed_revalidation_removes_prior_evidence_and_transport_errors_block(self):
        self.validate()
        self.responses[PR_PATH]["state"] = "closed"
        with self.assertRaises(ValueError):
            self.validate()
        self.assertFalse((self.output / "review-context.json").exists())
        self.assertFalse((self.output / "upstream.diff").exists())
        with self.assertRaises(OSError):
            gate.validate(42, self.output, api=Mock(side_effect=OSError("API unavailable")))
        self.assertFalse((self.output / "review-context.json").exists())

    def test_actions_trust_guard_requires_manual_main(self):
        for event, ref in [("pull_request", "refs/heads/main"), ("push", "refs/heads/main"),
                           ("schedule", "refs/heads/main"), ("workflow_dispatch", "refs/heads/evil")]:
            with patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": event, "GITHUB_REF": ref}), self.assertRaises(ValueError):
                self.validate()
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main"}):
            self.validate()

    def test_cli_validate_emits_only_trusted_scalar_outputs(self):
        output_file = self.output / "github-output"
        stdout = io.StringIO()
        argv = ["update-gate.py", "validate", "--pr", "42", "--output-dir", str(self.output),
                "--github-output", str(output_file)]
        with patch.object(gate, "github_api", self.api), patch("sys.argv", argv), redirect_stdout(stdout):
            gate.main()
        self.assertEqual(json.loads(stdout.getvalue())["head_sha"], HEAD)
        self.assertIn("head_sha=" + HEAD + "\n", output_file.read_text())
        self.assertNotIn("approved=", output_file.read_text())


def redate(text, date):
    # Replace only the new entry's date, preserving the base changelog verbatim.
    marker = " -- Maintainer Name <maintainer@example.org>  "
    before, after = text.split(marker, 1)
    _, separator, tail = after.partition("\n\n")
    return before + marker + date + separator + tail


class UpdateGateReviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "review.json"

    def review(self, assessment):
        self.path.write_text(json.dumps(assessment))
        return gate.review(HEAD, self.path)

    def test_accepts_exact_complete_safe_assessment_and_structured_output(self):
        self.assertEqual(self.review(ASSESSMENT), {"approved": "true"})
        self.assertEqual(self.review({"structured_output": ASSESSMENT, "result": "not instructions"}), {"approved": "true"})

    def test_block_findings_incomplete_stale_and_wrong_types_fail_closed(self):
        mutations = [{"head_sha": "9" * 40}, {"head_sha": "A" * 40}, {"decision": "block"},
                     {"decision": "approve\napproved=true"}, {"complete": False}, {"complete": "true"},
                     {"complete": 1}, {"high_critical_findings": ["critical issue"]},
                     {"blocking_findings": ["build is broken"]}, {"high_critical_findings": "none"},
                     {"blocking_findings": [1]}, {"summary": ""}, {"summary": {}}, {"extra": "injected"}]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.review({**ASSESSMENT, **mutation})
        for key in ASSESSMENT:
            with self.subTest(missing=key), self.assertRaises(ValueError):
                self.review({k: v for k, v in ASSESSMENT.items() if k != key})

    def test_malformed_truncated_duplicate_nan_and_json_injection_fail_closed(self):
        for text in ["", "{", '```json\n' + json.dumps(ASSESSMENT) + '\n```',
                     json.dumps(ASSESSMENT) + '\n{"approved":true}',
                     json.dumps(ASSESSMENT)[:-1] + ',"decision":"approve"}',
                     json.dumps(ASSESSMENT).replace('"complete": true', '"complete": NaN'),
                     '"approve"', '[]', '{"structured_output":"' + json.dumps(ASSESSMENT).replace('"', '\\"') + '"}']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.path.write_text(text)
                gate.review(HEAD, self.path)

    def test_reviewer_error_wrappers_block_even_with_an_approving_payload(self):
        for status in [{"is_error": True}, {"is_error": "false"}, {"subtype": "error_max_turns"},
                       {"error": "review failed"}, {"errors": ["failed"]}]:
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "Reviewer returned an error"):
                self.review({"structured_output": ASSESSMENT, **status})

    def test_review_and_field_size_bounds(self):
        for update in [{"summary": "x" * 8193}, {"summary": "x" + " " * 8192}, {"blocking_findings": ["x" * 4097]},
                       {"high_critical_findings": ["x"] * 101}]:
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.review({**ASSESSMENT, **update})
        self.path.write_bytes(b"x" * (gate.MAX_REVIEW_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "byte limit"):
            gate.review(HEAD, self.path)

    def test_real_cli_blocks_missing_file_or_malformed_assessment_without_echoing_data(self):
        output = Path(self.directory.name) / "github-output"
        command = [sys.executable, str(ROOT / "scripts/update-gate.py"), "review",
                   "--head-sha", HEAD, "--json-file", str(self.path), "--github-output", str(output)]
        for text in [None, "malicious source text that must not be echoed"]:
            if text is not None:
                self.path.write_text(text)
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertNotIn("malicious source", result.stderr)
            self.assertFalse(output.exists())

    def test_cli_writes_approval_only_after_success(self):
        output = Path(self.directory.name) / "github-output"
        argv = ["update-gate.py", "review", "--head-sha", HEAD, "--json-file", str(self.path)]
        self.path.write_text(json.dumps({**ASSESSMENT, "complete": False}))
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), patch("sys.argv", argv):
            with self.assertRaises(ValueError):
                gate.main()
        self.assertFalse(output.exists())
        self.path.write_text(json.dumps(ASSESSMENT))
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), patch("sys.argv", argv), redirect_stdout(io.StringIO()):
            gate.main()
        self.assertEqual(output.read_text(), "approved=true\n")


class UpdateGateApiTests(unittest.TestCase):
    def test_api_auth_pinned_media_and_bounded_reads(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"ok":true}'
        with patch.dict(os.environ, {"GH_TOKEN": "fixture-not-a-credential"}), patch.object(gate, "urlopen", return_value=response) as opener:
            self.assertEqual(gate.github_api("repos/owner/repo/tags"), {"ok": True})
            request = opener.call_args.args[0]
            self.assertEqual(request.full_url, "https://api.github.com/repos/owner/repo/tags")
            self.assertEqual(request.get_header("Authorization"), "Bearer fixture-not-a-credential")
            response.read.assert_called_with(gate.MAX_API_BYTES + 1)
            response.read.return_value = DIFF.encode()
            self.assertEqual(gate.github_api(COMPARE, diff=True), DIFF)
            self.assertEqual(opener.call_args.args[0].get_header("Accept"), "application/vnd.github.diff")
            response.read.return_value = b"x" * (gate.MAX_DIFF_BYTES + 1)
            with self.assertRaisesRegex(ValueError, "byte limit"):
                gate.github_api(COMPARE, diff=True)


if __name__ == "__main__":
    unittest.main()
