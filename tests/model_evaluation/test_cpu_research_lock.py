"""Regression checks for the reviewed CPU retrieval dependency lock."""

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "tools/model_evaluation/fashion_retrieval/requirements-research-py311-linux-x86_64-cpu.lock"
EXPECTED_LOCK_SHA256 = "28351b56bcb8604ad0c7499561364200f4b683a690f874a34566e494347ffcae"
REQUIRED_PINS = (
    "torch==2.7.0+cpu",
    "torchvision==0.22.0+cpu",
    "open-clip-torch==4.2.2",
    "transformers==4.57.6",
)


class CpuResearchLockTests(unittest.TestCase):
    def test_lock_digest_matches_reviewed_artifact(self) -> None:
        digest = hashlib.sha256(LOCK.read_bytes()).hexdigest()
        self.assertEqual(digest, EXPECTED_LOCK_SHA256)

    def test_every_requirement_is_hash_pinned(self) -> None:
        lines = LOCK.read_text(encoding="utf-8").splitlines()
        requirement_lines = [
            line for line in lines
            if line and not line.startswith(("#", "--", " ", "\\"))
        ]
        self.assertGreater(len(requirement_lines), 0)

        for line in requirement_lines:
            self.assertIn("==", line, line)
            package_version = line.split("==", 1)[1].strip().rstrip("\\\\").strip()
            self.assertTrue(package_version, line)
            self.assertNotIn(" ", package_version, line)

        hash_lines = [line for line in lines if "--hash=sha256:" in line]
        self.assertGreater(len(hash_lines), 0)
        for line in hash_lines:
            digest = line.split("--hash=sha256:", 1)[1].strip().rstrip("\\\\").strip()
            self.assertEqual(len(digest), 64, line)
            self.assertTrue(all(char in "0123456789abcdef" for char in digest), line)

        for requirement in requirement_lines:
            start = lines.index(requirement)
            block = [requirement]
            for continuation in lines[start + 1:]:
                if continuation.startswith("    --hash=sha256:"):
                    block.append(continuation)
                else:
                    break
            self.assertTrue(any("--hash=sha256:" in item for item in block), requirement)

    def test_required_cpu_runtime_versions_are_pinned(self) -> None:
        lines = LOCK.read_text(encoding="utf-8").splitlines()
        for pin in REQUIRED_PINS:
            self.assertTrue(any(line.startswith(pin + " ") or line == pin for line in lines), pin)


if __name__ == "__main__":
    unittest.main()
