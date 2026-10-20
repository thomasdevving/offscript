"""Export the FastAPI OpenAPI schema to packages/contracts/openapi.json (source for TypeScript types)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.main import create_app  # noqa: E402

schema = create_app().openapi()
out = ROOT / "packages" / "contracts" / "openapi.json"
out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {out} ({len(schema['components']['schemas'])} schemas)")
