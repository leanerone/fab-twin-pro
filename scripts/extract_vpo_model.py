"""Extract fallbackModel from public/VPO_3D.html into a clean JSON file."""
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parent.parent
src = root / "frontend" / "public" / "VPO_3D.html"
out_dir = root / "frontend" / "public" / "models"
out_dir.mkdir(parents=True, exist_ok=True)
out = out_dir / "vpo-2200-3d.json"

text = src.read_text(encoding="utf-8")

# Find the fallbackModel object literal
start = text.find("fallbackModel = {")
if start < 0:
    raise RuntimeError("fallbackModel not found")
start += len("fallbackModel = ")

# Find the end: the next top-level ";" after the matching braces or before stateColors
end = text.find("stateColors = {", start)
if end < 0:
    raise RuntimeError("end marker not found")

js_literal = text[start:end].strip().rstrip(",; \n")

# The literal uses JS object shorthand with bare keys; quote them for JSON.
# Replace any remaining !0 / !1 that may appear in nested flags.
js_literal = js_literal.replace(": !0", ": true").replace(": !1", ": false")

# Quote bare object keys (alphanumeric + underscore, possibly with dashes in strings already quoted)
js_literal = re.sub(r'(?<=[{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r' "\1":', js_literal)

# Remove trailing commas before closing braces/brackets
text_clean = re.sub(r',(\s*[}\]])', r'\1', js_literal)

try:
    model = json.loads(text_clean)
except json.JSONDecodeError as e:
    print(f"JSON parse error: {e}")
    # Fallback: try to extract just the parts array which is what we need.
    parts_start = text_clean.find('"parts":')
    if parts_start < 0:
        raise
    parts_end = text_clean.rfind("]") + 1
    parts_text = text_clean[parts_start:parts_end]
    parts_text = "{" + parts_text + "}"
    wrapper = json.loads(parts_text)
    model = {"version": "3.0.0", "model_id": "VPO-2200-01-photo-aligned-light-3d-v3.0", "units": "mm", "parts": wrapper["parts"]}

out.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Extracted {len(model.get('parts', []))} parts to {out}")
