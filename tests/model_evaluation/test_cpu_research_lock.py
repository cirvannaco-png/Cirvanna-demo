"""Regression checks for the reviewed CPU retrieval dependency lock."""

from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "tools/model_evaluation/fashion_retrieval/requirements-research-py311-linux-x86_64-cpu.lock"
EXPECTED_LOCK_SHA256 = "28351b56bcb8604ad0c7499561364200f4b683a690f874a34566e494347ffcae"
REQUIRED_PINS = {
    "torch": "2.7.0+cpu",
    "torchvision": "0.22.0+cpu",
    "open_clip_torch": "4.2.2",
    "transformers": "4.57.6",
}


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
            self.assertRegex(line, r"^[A-Za-z0-9_.-]+==[^\\s]+\\s+\\\\?$")

        hash_lines = [line for line in lines if "--hash=sha256:" in line]
        self.assertGreater(len(hash_lines), 0)
        for line in hash_lines:
            self.assertRegex(line, r"--hash=sha256:[0-9a-f]{64}")

        for line in requirement_lines:
            start = lines.index(line)
            block = [line]
            for continuation in lines[start + 1:]:
                if continuation.startswith("    --hash=sha256:"):
                    block.append(continuation)
                else:
                    break
            self.assertTrue(any("--hash=sha256:" in item for item in block), line)

    def test_required_cpu_runtime_versions_are_pinned(self) -> None:
        text = LOCK.read_text(encoding="utf-8")
        for package, version in REQUIRED_PINS.items():
            pattern = rf"(?m)^{re.escape(package)}=={re.escape(version)}(?:\\s|$)"
            self.assertRegex(text, pattern)


if __name__ == "__main__":
    unittest.main()
