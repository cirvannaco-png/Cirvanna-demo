from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher
import hashlib
import itertools
import csv

root = Path.home() / "cirvanna-reconstruction"
source_dir = root / "extracted"
manifest_path = root / "source-manifest.csv"

with manifest_path.open(encoding="utf-8", newline="") as f:
    entries = list(csv.DictReader(f))

files = []

for entry in entries:
    path = source_dir / entry["extracted_filename"]
    data = path.read_bytes()
    files.append({
        "name": entry["original_filename"],
        "path": path,
        "data": data,
        "hash": hashlib.sha256(data).hexdigest(),
        "lines": data.splitlines(),
    })

print("=== EXACT DUPLICATES ===")

hash_groups = defaultdict(list)
for item in files:
    hash_groups[item["hash"]].append(item["name"])

for group in hash_groups.values():
    if len(group) > 1:
        print("Identical:", " = ".join(group))

print("\n=== NEAR-DUPLICATE COMPARISON ===")

pairs = []

for a, b in itertools.combinations(files, 2):
    # Compare only sections with related names or matching
    # line counts to avoid noisy comparisons across unrelated files.
    an = Path(a["name"]).name.lower()
    bn = Path(b["name"]).name.lower()

    related_tokens = {
        token for token in an.replace(".", " ").split()
        if len(token) > 2
    } & {
        token for token in bn.replace(".", " ").split()
        if len(token) > 2
    }

    if not related_tokens and abs(
        len(a["lines"]) - len(b["lines"])
    ) > 5:
        continue

    if not a["lines"] or not b["lines"]:
        continue

    ratio = SequenceMatcher(
        None, a["lines"], b["lines"], autojunk=False
    ).ratio()

    if ratio >= 0.60:
        pairs.append((ratio, a["name"], b["name"]))

for ratio, a, b in sorted(pairs, reverse=True):
    print(f"{ratio:.1%} | {a} <-> {b}")

print("\n=== VIRTUAL TRY-ON CHECKSUMS ===")

for item in files:
    if "virtual tryon" in item["name"].lower():
        print(
            item["name"],
            "| lines:", len(item["lines"]),
            "| SHA-256:", item["hash"]
        )

print("\n=== REPORT COMPLETE ===")
