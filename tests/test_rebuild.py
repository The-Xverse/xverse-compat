"""Controlled-rebuild tests using only synthetic temporary Git repositories."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

from xverse_compat.rebuild import (
    ControlledRebuilder,
    RebuildError,
    RebuildManifest,
    write_result_exclusive,
)


class ControlledRebuildTests(unittest.TestCase):
    """Prove exact inputs, isolated stages, and fail-closed reproducibility."""

    def setUp(self) -> None:
        """Create one synthetic committed source, patch, and external builder."""
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git = Path(shutil.which("git") or "/usr/bin/git").resolve()
        self._git("init", "-q")
        self._git("config", "user.email", "fixture@example.invalid")
        self._git("config", "user.name", "Controlled Fixture")
        (self.source / "message.txt").write_text("fixed\n", encoding="utf-8")
        self._git("add", "message.txt")
        self._git("commit", "-q", "-m", "fixture")
        self.revision = self._git_text("rev-parse", "HEAD^{commit}")
        self.tree = self._git_text("rev-parse", "HEAD^{tree}")
        (self.source / "message.txt").write_text("configurable\n", encoding="utf-8")
        self.patch = self.root / "controlled.patch"
        self.patch.write_bytes(self._git_output("diff", "--", "message.txt"))
        self._git("checkout", "--", "message.txt")
        self.builder = self.root / "fixture-builder"
        self._write_builder(
            "from pathlib import Path\n"
            "Path('build').mkdir(exist_ok=True)\n"
            "Path('build/artifact.bin').write_bytes(Path('message.txt').read_bytes())\n"
        )
        self.raw = {
            "schemaVersion": 1,
            "sourceRevision": self.revision,
            "sourceTree": self.tree,
            "patchSha256": self._digest(self.patch.read_bytes()),
            "gitSha256": self._digest(self.git.read_bytes()),
            "toolSha256": {"fixture-builder": self._digest(self.builder.read_bytes())},
            "allowedPatchPaths": ["message.txt"],
            "steps": [{
                "executable": "fixture-builder",
                "arguments": [],
                "workingDirectory": ".",
                "timeoutSeconds": 10,
            }],
            "outputPath": "build/artifact.bin",
            "environment": {"BUILD_MODE": "controlled"},
            "metadata": {"decision": "fixture-only"},
        }

    def tearDown(self) -> None:
        """Remove all synthetic input and output data."""
        self.temporary.cleanup()

    def test_two_clean_builds_match_and_source_is_unchanged(self) -> None:
        """A valid rebuild emits matching digests and never patches the checkout."""
        before = (self.source / "message.txt").read_bytes()
        result = self._rebuild(self.raw, self.root / "work")
        self.assertEqual(result.attempt_digests[0], result.attempt_digests[1])
        self.assertEqual(result.artifact_sha256, self._digest(b"configurable\n"))
        self.assertEqual(before, (self.source / "message.txt").read_bytes())
        self.assertTrue((self.root / "work" / "attempt-a").is_dir())
        self.assertTrue((self.root / "work" / "attempt-b").is_dir())

    def test_dirty_checkout_content_is_not_staged(self) -> None:
        """Git archive excludes dirty working-tree content from both attempts."""
        (self.source / "untracked.txt").write_text("ambient", encoding="utf-8")
        result = self._rebuild(self.raw, self.root / "work")
        self.assertTrue(result.artifact_sha256.startswith("sha256:"))
        self.assertFalse((self.root / "work" / "attempt-a" / "untracked.txt").exists())

    def test_wrong_source_revision_fails(self) -> None:
        """Revision drift fails before the work root is created."""
        raw = self._changed(sourceRevision="0" * 40)
        self._assert_error("source-identity-mismatch", raw)

    def test_wrong_source_tree_fails(self) -> None:
        """Tree drift fails before the work root is created."""
        raw = self._changed(sourceTree="0" * 40)
        self._assert_error("source-identity-mismatch", raw)

    def test_wrong_patch_digest_fails(self) -> None:
        """Patch drift is distinguished from an invalid patch."""
        raw = self._changed(patchSha256="sha256:" + "0" * 64)
        self._assert_error("patch-digest-mismatch", raw)

    def test_manifest_rejects_traversal(self) -> None:
        """Declared paths cannot escape their isolated stage."""
        raw = self._changed(outputPath="../artifact")
        self._assert_manifest_error(raw)

    def test_manifest_rejects_private_environment_value(self) -> None:
        """Obvious private addressing cannot enter a public manifest."""
        raw = self._changed(environment={"ENDPOINT": "10." + "1.2.3"})
        self._assert_manifest_error(raw)

    def test_manifest_rejects_credential_shaped_value(self) -> None:
        """A benign key cannot smuggle an obvious credential into public metadata."""
        raw = self._changed(metadata={"note": "pass" + "word=redacted"})
        self._assert_manifest_error(raw)

    def test_manifest_rejects_secret_bearing_environment_name(self) -> None:
        """The envelope does not become a secret distribution mechanism."""
        raw = self._changed(environment={"ACCESS_TOKEN": "redacted"})
        self._assert_manifest_error(raw)

    def test_manifest_rejects_unknown_placeholder(self) -> None:
        """Build arguments support only declared literal placeholders."""
        raw = copy.deepcopy(self.raw)
        raw["steps"][0]["arguments"] = ["{unknown}"]
        self._assert_manifest_error(raw)

    def test_manifest_rejects_duplicate_keys(self) -> None:
        """Duplicate JSON keys cannot alter interpretation between readers."""
        content = (
            '{"schemaVersion":1,"schemaVersion":1,"sourceRevision":"'
            + self.revision
            + '"}'
        ).encode()
        with self.assertRaises(RebuildError) as caught:
            RebuildManifest.from_json_bytes(content)
        self.assertEqual(caught.exception.code, "manifest-invalid")

    def test_patch_target_outside_allowlist_fails(self) -> None:
        """Patch digest acceptance never broadens the declared target set."""
        raw = self._changed(allowedPatchPaths=["different.txt"])
        self._assert_error("patch-target-denied", raw)

    def test_patch_header_cannot_disagree_with_diff_target(self) -> None:
        """Every old/new patch header is bound to the same allowlisted path."""
        content = self.patch.read_text(encoding="utf-8").replace(
            "+++ b/message.txt", "+++ b/different.txt"
        )
        self.patch.write_text(content, encoding="utf-8")
        raw = self._changed(patchSha256=self._digest(self.patch.read_bytes()))
        raw["allowedPatchPaths"] = ["message.txt", "different.txt"]
        self._assert_error("patch-invalid", raw)

    def test_relative_tool_path_fails(self) -> None:
        """Build executable selection cannot use ambient path lookup."""
        with self.assertRaises(RebuildError) as caught:
            ControlledRebuilder(self.git, {"fixture-builder": Path("fixture-builder")})
        self.assertEqual(caught.exception.code, "build-command-denied")

    def test_unmapped_tool_fails(self) -> None:
        """A valid manifest cannot invoke a logical tool absent from the allowlist."""
        raw = copy.deepcopy(self.raw)
        raw["steps"][0]["executable"] = "other-builder"
        raw["toolSha256"] = {"other-builder": self._digest(self.builder.read_bytes())}
        self._assert_error("build-command-denied", raw)

    def test_changed_tool_digest_fails_before_staging(self) -> None:
        """The exact executable bytes are an input to the rebuild decision."""
        self._write_builder("pass\n")
        self._assert_error("tool-identity-mismatch", self.raw)

    def test_attempt_dependent_output_fails_reproducibility(self) -> None:
        """Attempt-specific output bytes prevent artifact acceptance."""
        self._write_builder(
            "from pathlib import Path\nimport sys\n"
            "Path('build').mkdir(exist_ok=True)\n"
            "Path('build/artifact.bin').write_text(sys.argv[1])\n"
        )
        raw = copy.deepcopy(self.raw)
        raw["steps"][0]["arguments"] = ["{attempt}"]
        self._sync_tool_digest(raw)
        self._assert_error("reproducibility-mismatch", raw)

    def test_missing_output_fails(self) -> None:
        """A zero-status builder must still produce the exact declared output."""
        self._write_builder("pass\n")
        raw = copy.deepcopy(self.raw)
        self._sync_tool_digest(raw)
        self._assert_error("output-invalid", raw)

    def test_symbolic_link_output_fails(self) -> None:
        """An output symbolic link cannot escape artifact ownership."""
        self._write_builder(
            "from pathlib import Path\n"
            "Path('build').mkdir(exist_ok=True)\n"
            "Path('outside').write_bytes(b'x')\n"
            "Path('build/artifact.bin').symlink_to('../outside')\n"
        )
        raw = copy.deepcopy(self.raw)
        self._sync_tool_digest(raw)
        self._assert_error("output-invalid", raw)

    def test_existing_work_root_fails(self) -> None:
        """A rebuild never reuses a potentially contaminated work root."""
        work = self.root / "work"
        work.mkdir()
        manifest = self._manifest(self.raw)
        rebuilder = ControlledRebuilder(self.git, {"fixture-builder": self.builder})
        with self.assertRaises(RebuildError) as caught:
            rebuilder.rebuild(manifest, self.source, self.patch, work)
        self.assertEqual(caught.exception.code, "stage-failed")

    def test_failed_builder_removes_partial_work_root(self) -> None:
        """A failed command cannot leave a stage that appears accepted."""
        self._write_builder("raise SystemExit(3)\n")
        raw = copy.deepcopy(self.raw)
        self._sync_tool_digest(raw)
        self._assert_error("build-failed", raw)

    def test_builder_timeout_is_bounded_and_cleans_stage(self) -> None:
        """A step exceeding its declared ceiling fails and removes both stages."""
        self._write_builder("import time\ntime.sleep(5)\n")
        raw = copy.deepcopy(self.raw)
        raw["steps"][0]["timeoutSeconds"] = 1
        self._sync_tool_digest(raw)
        started = time.monotonic()
        self._assert_error("build-failed", raw)
        self.assertLess(time.monotonic() - started, 4)

    def test_result_contains_no_host_or_command_details(self) -> None:
        """Canonical public evidence is limited to identities and safe metadata."""
        result = self._rebuild(self.raw, self.root / "work").canonical()
        encoded = json.dumps(result)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn("BUILD_MODE", encoded)
        self.assertIn("gitSha256", result)
        self.assertIn("toolSha256", result)
        self.assertTrue(result["reproducible"])

    def test_result_writer_creates_once_and_refuses_replacement(self) -> None:
        """Atomic evidence creation cannot overwrite a prior result."""
        result = self._rebuild(self.raw, self.root / "work")
        destination = self.root / "result.json"
        write_result_exclusive(destination, result)
        original = destination.read_bytes()
        with self.assertRaises(RebuildError) as caught:
            write_result_exclusive(destination, result)
        self.assertEqual(caught.exception.code, "result-write-failed")
        self.assertEqual(destination.read_bytes(), original)

    def _assert_error(self, code: str, raw: dict[str, object]) -> None:
        """Assert a rebuild code and cleanup of a fresh work root."""
        work = self.root / "work"
        with self.assertRaises(RebuildError) as caught:
            self._rebuild(raw, work)
        self.assertEqual(caught.exception.code, code)
        self.assertFalse(work.exists())

    def _assert_manifest_error(self, raw: dict[str, object]) -> None:
        """Assert strict manifest validation failure."""
        with self.assertRaises(RebuildError) as caught:
            self._manifest(raw)
        self.assertEqual(caught.exception.code, "manifest-invalid")

    def _rebuild(self, raw: dict[str, object], work: Path):
        """Build from one raw manifest using exact fixture tools."""
        manifest = self._manifest(raw)
        rebuilder = ControlledRebuilder(self.git, {"fixture-builder": self.builder})
        return rebuilder.rebuild(manifest, self.source, self.patch, work)

    @staticmethod
    def _manifest(raw: dict[str, object]) -> RebuildManifest:
        """Serialize and parse through the public strict manifest boundary."""
        return RebuildManifest.from_json_bytes(json.dumps(raw).encode())

    def _changed(self, **changes: object) -> dict[str, object]:
        """Return a deep-copied raw manifest with selected field changes."""
        raw = copy.deepcopy(self.raw)
        raw.update(changes)
        return raw

    def _sync_tool_digest(self, raw: dict[str, object]) -> None:
        """Update a test manifest after intentionally changing its fixture tool."""
        raw["toolSha256"] = {"fixture-builder": self._digest(self.builder.read_bytes())}

    def _write_builder(self, body: str) -> None:
        """Write an external absolute fixture builder with a fixed interpreter."""
        self.builder.write_text("#!/usr/bin/python3\n" + body, encoding="utf-8")
        self.builder.chmod(0o700)

    def _git(self, *arguments: str) -> None:
        """Run fixture Git setup without exposing command output."""
        subprocess.run(
            [str(self.git), "-C", str(self.source), *arguments],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _git_text(self, *arguments: str) -> str:
        """Return one fixture Git identity."""
        return self._git_output(*arguments).decode("ascii").strip()

    def _git_output(self, *arguments: str) -> bytes:
        """Capture fixture Git bytes."""
        return subprocess.run(
            [str(self.git), "-C", str(self.source), *arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ).stdout

    @staticmethod
    def _digest(content: bytes) -> str:
        """Return a contract-form SHA-256 digest."""
        return "sha256:" + hashlib.sha256(content).hexdigest()


if __name__ == "__main__":
    unittest.main()
