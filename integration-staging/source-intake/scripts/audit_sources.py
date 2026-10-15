from pathlib import Path
from collections import Counter
import csv
import hashlib
import re

root = Path.home() / "cirvanna-reconstruction"
source_dir = root / "extracted"
manifest_path = root / "source-manifest.csv"
report_path = root / "source-audit.csv"

with manifest_path.open(encoding="utf-8", newline="") as f:
    manifest = list(csv.DictReader(f))

hash_groups = {}
records = []

for item in manifest:
    path = source_dir / item["extracted_filename"]
    data = path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()

    digest = hashlib.sha256(data).hexdigest()
    hash_groups.setdefault(digest, []).append(
        item["original_filename"]
    )

    languages = Counter(
        match.group(1).strip().lower()
        for match in re.finditer(
            r"(?m)^```([^\n`]*)", text
        )
    )

    paths = []
    for line in lines:
        candidate = line.strip().strip("`").strip()
        candidate = candidate.removeprefix("FILE:")
        if re.search(
            r"(^|[/\\])[^/\\]+\."
            r"(py|ts|tsx|js|jsx|json|yaml|yml|"
            r"md|sql|html|css|sh|toml)$",
            candidate,
            re.I,
        ):
            paths.append(candidate)

    records.append({
        "section": item["section_number"],
        "original_filename": item["original_filename"],
        "extracted_filename": item["extracted_filename"],
        "bytes": len(data),
        "lines": len(lines),
        "sha256": digest,
        "fenced_code_blocks": sum(languages.values()),
        "code_languages": "; ".join(
            f"{lang or '(unspecified)'}:{count}"
            for lang, count in languages.most_common()
        ),
        "possible_paths": " | ".join(dict.fromkeys(paths[:30])),
        "exact_duplicate_sources": " | ".join(
            hash_groups[digest]
        ),
    })

with report_path.open("x", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=records[0].keys())
    writer.writeheader()
    writer.writerows(records)

print(f"Sections audited: {len(records)}")
print(f"Audit report: {report_path}")
print("\nSECTION SUMMARY")
for r in records:
    print(
        f"{int(r['section']):02d} | "
        f"{r['original_filename']} | "
        f"{r['lines']} lines | "
        f"{r['fenced_code_blocks']} code blocks"
    )

print("\nEXACT DUPLICATES")
for names in hash_groups.values():
    if len(names) > 1:
        print(" = ".join(names))
