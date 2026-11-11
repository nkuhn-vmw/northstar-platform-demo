from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
LOADER = importlib.machinery.SourceFileLoader("northstar_prepare", str(ROOT / "bin" / "prepare"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
prepare = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(prepare)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class PrepareTests(unittest.TestCase):
    def make_archive(self, directory: Path, member: str, content: bytes) -> Path:
        source = directory / "payload"
        source.write_bytes(content)
        archive = directory / "fixture.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(source, arcname=member)
        return archive

    def dependency(self, archive: Path, member: str, content: bytes) -> dict:
        return {
            "id": "fixture",
            "kind": "release-archive",
            "version": "v1",
            "source": {
                "url": "https://downloads.example.invalid/fixture.tar.gz",
                "archive_filename": archive.name,
                "archive_sha256": prepare.sha256_file(archive),
            },
            "archive_member": member,
            "output": {
                "path": ".artifacts/fixture",
                "sha256": digest(content),
                "mode": "0755",
            },
        }

    def test_offline_preparation_uses_real_temp_archive_and_check(self) -> None:
        with tempfile.TemporaryDirectory() as root_name, tempfile.TemporaryDirectory() as offline_name:
            root = Path(root_name)
            offline = Path(offline_name)
            content = b"#!/bin/sh\nprintf 'fixture\\n'\n"
            archive = self.make_archive(offline, "release/fixture", content)
            dependency = self.dependency(archive, "release/fixture", content)

            records = prepare.prepare_all(root, [dependency], offline)

            output = root / ".artifacts" / "fixture"
            self.assertEqual(output.read_bytes(), content)
            self.assertEqual(output.stat().st_mode & 0o777, 0o755)
            self.assertEqual(records["fixture"]["output_sha256"], digest(content))
            state = json.loads((root / ".artifacts" / "prepare-state.json").read_text())
            self.assertEqual(state["target"], "linux/amd64")
            prepare.check_all(root, [dependency])

    def test_offline_preparation_rejects_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as root_name, tempfile.TemporaryDirectory() as offline_name:
            root = Path(root_name)
            offline = Path(offline_name)
            content = b"fixture"
            archive = self.make_archive(offline, "fixture", content)
            dependency = self.dependency(archive, "fixture", content)
            dependency["source"]["archive_sha256"] = "0" * 64

            with self.assertRaisesRegex(prepare.PrepareError, "archive fixture.tar.gz SHA-256 mismatch"):
                prepare.prepare_all(root, [dependency], offline)
            self.assertFalse((root / ".artifacts" / "fixture").exists())

    def test_offline_preparation_reports_missing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as root_name, tempfile.TemporaryDirectory() as offline_name:
            root = Path(root_name)
            offline = Path(offline_name)
            placeholder = offline / "fixture.tar.gz"
            placeholder.write_bytes(b"fixture")
            dependency = self.dependency(placeholder, "fixture", b"fixture")
            placeholder.unlink()

            with self.assertRaisesRegex(prepare.PrepareError, "offline artifact is missing"):
                prepare.prepare_all(root, [dependency], offline)

    def test_check_detects_prepared_output_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as root_name, tempfile.TemporaryDirectory() as offline_name:
            root = Path(root_name)
            offline = Path(offline_name)
            content = b"fixture"
            archive = self.make_archive(offline, "fixture", content)
            dependency = self.dependency(archive, "fixture", content)
            prepare.prepare_all(root, [dependency], offline)
            (root / ".artifacts" / "fixture").write_bytes(b"tampered")

            with self.assertRaisesRegex(prepare.PrepareError, "prepared output SHA-256 mismatch"):
                prepare.check_all(root, [dependency])

    def test_source_tree_hash_ignores_generated_output_directories(self) -> None:
        with tempfile.TemporaryDirectory() as root_name:
            root = Path(root_name)
            (root / "main.go").write_text("package main\n")
            initial = prepare.source_tree_sha256(root)
            (root / "build" / "libs").mkdir(parents=True)
            (root / "build" / "libs" / "app.jar").write_bytes(b"generated")
            (root / "target").mkdir()
            (root / "target" / "app.jar").write_bytes(b"generated")
            self.assertEqual(prepare.source_tree_sha256(root), initial)

    def test_dependency_manifest_names_all_deployable_outputs(self) -> None:
        manifest_text = (ROOT / "provenance" / "dependencies.json").read_text()
        self.assertNotIn("/Users/", manifest_text)
        manifest = json.loads(manifest_text)
        outputs = {item["id"]: item["output"]["path"] for item in manifest["dependencies"]}
        self.assertEqual(outputs["northstar-market"], "apps/market/build/libs/northstar-market.jar")



if __name__ == "__main__":
    unittest.main()


class ToolchainPatchTests(unittest.TestCase):
    def test_preparation_rejects_an_older_security_patch(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'go.mod').write_text('module example.test/demo\n\ngo 1.27.4\n')
            dependencies = [{'kind': 'go-build', 'source': {'path': '.'}}]
            with patch.object(prepare, '_go_version', return_value=(1, 27, 3)):
                with self.assertRaisesRegex(prepare.PrepareError, '1.27.4'):
                    prepare.validate_prerequisites(root, dependencies)
            with patch.object(prepare, '_go_version', return_value=(1, 27, 4)):
                prepare.validate_prerequisites(root, dependencies)
