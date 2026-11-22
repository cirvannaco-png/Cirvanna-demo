import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.model_evaluation.fashion_retrieval.private_artifacts import (
    ensure_private_targets_available,
    write_private_text,
)


class PrivateArtifactWriterTests(unittest.TestCase):
    def test_creates_owner_only_file_and_private_new_directory_on_posix(self):
        if os.name != "posix":
            self.skipTest("POSIX permission bits are not portable")
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "restricted" / "nested" / "rankings.jsonl"
            write_private_text(destination, "private\n")
            self.assertEqual(destination.read_text(), "private\n")
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            self.assertEqual(destination.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(destination.parent.parent.stat().st_mode & 0o777, 0o700)

    def test_new_private_directory_can_be_created_under_shared_parent(self):
        if os.name != "posix":
            self.skipTest("POSIX permission bits are not portable")
        with tempfile.TemporaryDirectory() as temp:
            shared_parent = Path(temp) / "shared"
            shared_parent.mkdir()
            os.chmod(shared_parent, 0o755)
            destination = shared_parent / "restricted" / "rankings.jsonl"
            write_private_text(destination, "private")
            self.assertEqual(destination.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

    def test_preflight_checks_all_targets_before_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "rankings.jsonl"
            manifest = Path(temp) / "rankings.jsonl.manifest.json"
            manifest.write_text("existing manifest")
            with self.assertRaises(FileExistsError):
                ensure_private_targets_available([output, manifest])
            self.assertFalse(output.exists())

    def test_preflight_allows_explicit_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "rankings.jsonl"
            output.write_text("existing")
            ensure_private_targets_available([output], overwrite=True)

    def test_refuses_existing_destination_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "artifact.jsonl"
            destination.write_text("original")
            with self.assertRaises(FileExistsError):
                write_private_text(destination, "replacement")
            self.assertEqual(destination.read_text(), "original")

    def test_overwrite_is_atomic_and_replaces_content(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "artifact.jsonl"
            write_private_text(destination, "original")
            write_private_text(destination, "replacement", overwrite=True)
            self.assertEqual(destination.read_text(), "replacement")
            self.assertEqual(list(Path(temp).glob("*.tmp")), [])

    def test_failed_write_does_not_leave_destination_or_temporary_file(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "artifact.jsonl"
            with patch("tools.model_evaluation.fashion_retrieval.private_artifacts.os.fsync", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    write_private_text(destination, "private")
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(temp).glob(".*.tmp")), [])

    def test_rejects_group_or_world_accessible_existing_directory_on_posix(self):
        if os.name != "posix":
            self.skipTest("POSIX permission bits are not portable")
        with tempfile.TemporaryDirectory() as temp:
            os.chmod(temp, 0o755)
            with self.assertRaisesRegex(PermissionError, "group/other permissions"):
                write_private_text(Path(temp) / "artifact.jsonl", "private")




if __name__ == "__main__":
    unittest.main()
