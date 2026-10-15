from pathlib import Path
import csv
import hashlib
import re
import sys

archive = Path.home() / "storage/downloads/cirvanna-source.txt"
output = Path.home() / "cirvanna-reconstruction/extracted"
manifest = Path.home() / "cirvanna-reconstruction/source-manifest.csv"

if not archive.is_file():
    sys.exit(f"ERROR: Source archive not found: {archive}")

output.mkdir(parents=True, exist_ok=True)

data = archive.read_bytes()
lines = data.splitlines(keepends=True)

header_pattern = re.compile(
    rb"^===== FILE: (.*?) =====[ \t]*(?:\r?\n)?$"
)

sections = []
current_name = None
current_content = []

for line in lines:
    match = header_pattern.match(line)

    if match:
        if current_name is not None:
            sections.append((
                current_name,
                b"".join(current_content)
            ))

        current_name = match.group(1).decode(
            "utf-8", errors="replace"
        )
        current_content = []
    elif current_name is not None:
        current_content.append(line)

if current_name is not None:
    sections.append((
        current_name,
        b"".join(current_content)
    ))

if not sections:
    sys.exit(
        "ERROR: No source sections found. "
        "The archive format needs inspection."
    )

if len(sections) != 31:
    print(
        f"WARNING: Expected 31 sections, found {len(sections)}."
    )

records = []

for index, (original_name, content) in enumerate(
    sections, start=1
):
    original_path = Path(original_name)
    original_filename = original_path.name or "unnamed"

    # Produce a safe filename without changing the recorded
    # original filename.
    safe_name = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        original_filename
    ).strip("._")

    if not safe_name:
        safe_name = "unnamed.txt"

    extracted_name = f"{index:04d}__{safe_name}"
    destination = output / extracted_name

    # Never overwrite an existing extraction.
    if destination.exists():
        sys.exit(
            f"ERROR: Destination already exists: {destination}\n"
            "Inspect the existing extraction before retrying."
        )

    destination.write_bytes(content)

    records.append({
        "section_number": index,
        "original_filename": original_name,
        "extracted_filename": extracted_name,
        "byte_count": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    })

with manifest.open(
    "x", newline="", encoding="utf-8"
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "section_number",
            "original_filename",
            "extracted_filename",
            "byte_count",
            "sha256",
        ],
    )
    writer.writeheader()
    writer.writerows(records)

print(f"Archive: {archive}")
print(f"Sections extracted: {len(records)}")
print(f"Extraction directory: {output}")
print(f"Manifest: {manifest}")
print("Original archive was not modified.")
print()

for record in records:
    print(
        f"{record['section_number']:02d}. "
        f"{record['original_filename']} -> "
        f"{record['extracted_filename']} "
        f"({record['byte_count']} bytes)"
    )
