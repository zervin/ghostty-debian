import importlib.util
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_metadata", ROOT / "scripts/release-metadata.py")
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)


class ReleaseMetadataTests(unittest.TestCase):
    def test_release_conf_identifiers(self):
        self.assertEqual(metadata.identifiers((ROOT / "release.conf").read_text()),
                         ("1.4.0-1personal1~deb13u1", "ghostty-1.4.0-1personal1-deb13u1"))

    def test_reject_injection_and_unstable_versions(self):
        for value in ["$(touch /tmp/no)", "1.4.0\nX=bad", "nightly", "1.4.0-1personal1~deb13u1;id", "1.4.0-1personal1~deb13u1\nx"]:
            with self.subTest(value=value), self.assertRaises((ValueError, KeyError)):
                metadata.identifiers(f"GHOSTTY_VERSION=1.4.0\nDEBIAN_VERSION={value}\n")

    def test_reject_version_mismatch(self):
        with self.assertRaises(ValueError):
            metadata.identifiers("GHOSTTY_VERSION=1.3.0\nDEBIAN_VERSION=1.4.0-1personal1~deb13u1\n")

    def test_github_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            subprocess.run(["python3", "scripts/release-metadata.py"], cwd=ROOT,
                           env={**os.environ, "GITHUB_OUTPUT": str(output)}, check=True)
            self.assertEqual(output.read_text(), "version=1.4.0-1personal1~deb13u1\ntag=ghostty-1.4.0-1personal1-deb13u1\n")


class CollectLicensesTests(unittest.TestCase):
    def test_preserves_paths_not_symlinks_or_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            for relative in ["LICENSE", "fonts/OFL.txt", "debian/staged/LICENSE", "cache/p/hash/LICENSE", "cache/p/hash/NOTICE"]:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(relative)
            (root / "linked-LICENSE").symlink_to("LICENSE")
            subprocess.run(["python3", str(ROOT / "debian/collect-licenses.py")], cwd=root,
                           env={**os.environ, "ZIG_GLOBAL_CACHE_DIR": str(cache)}, check=True)
            out = root / "debian/bundled-licenses"
            self.assertEqual((out / "source/fonts/OFL.txt").read_text(), "fonts/OFL.txt")
            self.assertEqual((out / "zig-cache/hash/NOTICE").read_text(), "cache/p/hash/NOTICE")
            self.assertFalse((out / "source/debian").exists())
            self.assertFalse((out / "source/linked-LICENSE").exists())


class SecurityInvariantsTests(unittest.TestCase):
    def test_workflow_manual_pinned_separated(self):
        text = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("workflow_dispatch:", text)
        for trigger in ["pull_request:", "pull_request_target:", "push:", "schedule:"]:
            self.assertNotIn(trigger, text)
        actions = re.findall(r"uses: (\S+)", text)
        self.assertEqual(len(actions), 3)
        for action in actions:
            self.assertRegex(action, r"^actions/(checkout|upload-artifact|download-artifact)@[a-f0-9]{40}$")
        self.assertIn("persist-credentials: false", text)
        self.assertIn("if: github.ref == 'refs/heads/main'", text)
        publish = text.split("  publish:", 1)[1]
        self.assertNotIn("checkout@", publish)
        self.assertNotIn("scripts/", publish)
        self.assertIn('--target "$TARGET_SHA" --draft', publish)
        self.assertNotRegex(text, r"run:.*\$\{\{")

    def test_pinned_base_and_offline_compile(self):
        config = (ROOT / "release.conf").read_text()
        dockerfile = (ROOT / "Dockerfile").read_text()
        base = re.search(r"^DEBIAN_IMAGE=(.+)$", config, re.M)[1]
        self.assertRegex(base, r"^debian:trixie-slim@sha256:[a-f0-9]{64}$")
        self.assertIn(base, dockerfile)
        build = (ROOT / "scripts/build.sh").read_text()
        self.assertIn("--network none", build)
        self.assertIn("--user 1000:1000 --read-only", build)
        self.assertIn("dst=/repo,readonly", build)
        self.assertNotIn("docker.sock", build)
        rules = (ROOT / "debian/rules").read_text()
        self.assertNotIn("--system", rules)
        for option in ["-Doptimize=ReleaseSafe", "-Dcpu=baseline", "-Dpie=true", "-Dsentry=false", "-fno-sys=gtk4-layer-shell", "-Demit-docs", "-Dversion-string=1.4.0"]:
            self.assertIn(option, rules)

    def test_no_handwritten_maintainer_scripts(self):
        for name in ["preinst", "postinst", "prerm", "postrm"]:
            self.assertFalse((ROOT / "debian" / name).exists())


if __name__ == "__main__":
    unittest.main()
