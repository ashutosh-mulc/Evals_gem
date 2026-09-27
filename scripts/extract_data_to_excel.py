#!/usr/bin/env python3
"""Extract dataset records from a .jsonl file and export to .xlsx or .csv.

Supports two output formats:
  - .xlsx  — images are decoded from base64 and embedded directly into cells
  - .csv   — text fields only (binary image/audio data omitted; file paths
             included as references)

Dataset JSONL structure (e.g. dataset-app-eval-heirarchical-v1.3.jsonl):
  - Line 1 (header): a JSON dict with "version" and "fields" keys -> skipped.
  - Subsequent lines: each line is a JSON dict (or a JSON list of dicts).

Usage:
    python3 scripts/extract_data_to_excel.py <dataset.jsonl> [output.xlsx|output.csv]

If no output path is given, defaults to the input path with the extension
replaced by .xlsx.
"""

import base64
import csv
import io
import json
import os
import sys

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# All fields to extract, in output column order.
# (output_column_name, dataset_key, include_in_csv)
FIELDS = [
    ("eval_id",        "eval_id",        True),
    ("eval_type",      "eval_type",      True),
    ("question_type",  "question_type",  True),
    ("question",       "question",       True),
    ("gt_answer",      "gt_answer",      True),
    ("image_path",     "image_path",     True),
    ("audio_path",     "audio_path",     True),
    ("audio_duration", "audio_duration", True),
    ("image",          "image",          False),  # base64 — xlsx only (embedded)
]

# Display size (in pixels) for embedded images in xlsx
IMAGE_DISPLAY_HEIGHT_PX = 150
IMAGE_DISPLAY_WIDTH_PX = 150
# openpyxl row height is in points (1pt ~= 1.333px)
ROW_HEIGHT_POINTS = IMAGE_DISPLAY_HEIGHT_PX * 0.75 + 5
IMAGE_COLUMN_WIDTH = 28  # column width units, roughly fits 150px


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_records(path):
    """Load a dataset .jsonl file, skipping the header line.

    Each data line is expected to be a JSON dict (or a JSON list of dicts).
    Returns a flat list of record dicts.
    """
    records = []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        return records

    # First line is the header; detect & skip it (contains "version"/"fields").
    first = lines[0].strip()
    if first:
        try:
            header_obj = json.loads(first)
            if isinstance(header_obj, dict) and (
                "version" in header_obj or "fields" in header_obj
            ):
                data_lines = lines[1:]
            else:
                data_lines = lines
        except json.JSONDecodeError:
            data_lines = lines
    else:
        data_lines = lines

    for line in data_lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    records.append(item)
        elif isinstance(obj, dict):
            records.append(obj)
    return records


# ---------------------------------------------------------------------------
# Image decoding (xlsx only)
# ---------------------------------------------------------------------------

def decode_image_bytes(b64_str):
    """Decode a base64-encoded image string into a PNG BytesIO buffer.

    Returns a BytesIO ready for openpyxl, or None on failure.
    """
    try:
        from PIL import Image as PILImage
    except ImportError:
        print("Warning: Pillow not installed — images cannot be embedded.", file=sys.stderr)
        return None

    try:
        raw = base64.b64decode(b64_str)
        img = PILImage.open(io.BytesIO(raw))
        # Resize to display size while preserving aspect ratio
        max_side = max(IMAGE_DISPLAY_WIDTH_PX, IMAGE_DISPLAY_HEIGHT_PX)
        if max(img.size) > max_side:
            ratio = max_side / float(max(img.size))
            new_size = (
                max(1, int(img.size[0] * ratio)),
                max(1, int(img.size[1] * ratio)),
            )
            img = img.resize(new_size, PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Warning: failed to decode image: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

def build_csv(records, output_path):
    """Write records to a CSV file (text fields only, no binary data)."""
    headers = [col for col, _key, in_csv in FIELDS if in_csv]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for rec in records:
            row = []
            for col, key, in_csv in FIELDS:
                if not in_csv:
                    continue
                val = rec.get(key, "")
                if val is None:
                    val = ""
                row.append(str(val))
            writer.writerow(row)
    print(f"CSV file saved to: {output_path}")


# ---------------------------------------------------------------------------
# XLSX writer
# ---------------------------------------------------------------------------

def build_xlsx(records, output_path):
    """Build the Excel workbook from records and save to output_path."""
    try:
        from openpyxl import Workbook
        from openpyxl.drawing.image import Image as XlImage
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter
    except ImportError:
        print("Error: openpyxl not installed. Install with: pip install openpyxl", file=sys.stderr)
        sys.exit(1)

    wb = Workbook()
    ws = wb.active
    ws.title = "dataset"

    # All output column headers (including image)
    headers = [col for col, _key, _in_csv in FIELDS]

    # Write header row
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        ws.cell(row=1, column=col_idx).font = Font(bold=True)

    # Configure image column
    image_col_idx = headers.index("image") + 1
    image_col_letter = get_column_letter(image_col_idx)
    ws.column_dimensions[image_col_letter].width = IMAGE_COLUMN_WIDTH

    total = len(records)
    images_embedded = 0
    errors = 0

    for i, rec in enumerate(records, start=1):
        row_idx = i + 1  # +1 for header row

        # Build the text row values. The image column is left blank because the
        # actual image is embedded as a drawing on top of the cell.
        row_values = []
        for col, key, _in_csv in FIELDS:
            if col == "image":
                row_values.append("")
                continue
            val = rec.get(key, "")
            if val is None:
                val = ""
            row_values.append(str(val))
        ws.append(row_values)

        # Set row height to accommodate the image
        ws.row_dimensions[row_idx].height = ROW_HEIGHT_POINTS

        # Embed image
        b64_img = rec.get("image", "")
        if b64_img:
            img_buf = decode_image_bytes(b64_img)
            if img_buf is not None:
                try:
                    xl_img = XlImage(img_buf)
                    cell_ref = f"{image_col_letter}{row_idx}"
                    ws.add_image(xl_img, cell_ref)
                    images_embedded += 1
                except Exception:
                    errors += 1
            else:
                errors += 1

        if i % 50 == 0:
            print(f"  Processed {i}/{total} records...")

    print(f"\n=== Summary ===")
    print(f"Total records: {total}")
    print(f"Images embedded: {images_embedded}")
    if errors:
        print(f"Records with image errors: {errors}")

    wb.save(output_path)
    print(f"Excel file saved to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(
            "Usage: python3 scripts/extract_data_to_excel.py "
            "<dataset.jsonl> [output.xlsx|output.csv]"
        )
        sys.exit(1)

    input_path = sys.argv[1]
    if not os.path.exists(input_path):
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    # Determine output path
    if len(sys.argv) > 2:
        output_path = sys.argv[2]
    else:
        base = os.path.splitext(input_path)[0]
        output_path = base + ".xlsx"

    # Ensure output directory exists
    out_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(out_dir, exist_ok=True)

    print(f"Loading records from: {input_path}")
    records = load_records(input_path)
    print(f"Loaded {len(records)} records.")

    if not records:
        print("No records found. Exiting.")
        sys.exit(0)

    # Dispatch based on output extension
    ext = os.path.splitext(output_path)[1].lower()
    if ext == ".csv":
        build_csv(records, output_path)
    elif ext == ".xlsx":
        build_xlsx(records, output_path)
    else:
        print(f"Error: unsupported output format '{ext}'. Use .xlsx or .csv")
        sys.exit(1)


if __name__ == "__main__":
    main()
