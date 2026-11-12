"""Write the files produced by export.html (window.build()) to v7/svg, v7/png and v7/favicon.ico.

Usage: python write.py <export.json>
"""
import base64
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # docs/design/logo/v7

raw = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
data = json.loads(raw) if isinstance(raw, str) else raw

svg_dir, png_dir = HERE / "svg", HERE / "png"
svg_dir.mkdir(exist_ok=True)
png_dir.mkdir(exist_ok=True)

for name, text in data["svgs"].items():
    (svg_dir / name).write_text(text, encoding="utf-8")

pngs = {name: base64.b64decode(b64) for name, b64 in data["pngs"].items()}
for name, blob in pngs.items():
    if not name.startswith("favicon-"):
        (png_dir / name).write_bytes(blob)

# favicon.ico with PNG-compressed 16/32/48 entries (supported by every current browser).
entries = [(n, pngs[f"favicon-{n}.png"]) for n in (16, 32, 48)]
header = struct.pack("<HHH", 0, 1, len(entries))
offset = 6 + 16 * len(entries)
table, body = b"", b""
for size, blob in entries:
    table += struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(blob), offset + len(body))
    body += blob
(HERE / "favicon.ico").write_bytes(header + table + body)

print(f"{len(data['svgs'])} svg, {len(pngs) - 3} png, favicon.ico ({len(entries)} sizes)")
