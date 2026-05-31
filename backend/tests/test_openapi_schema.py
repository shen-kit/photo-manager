from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "backend" / "openapi-schema.json"
EXPORT_SCRIPT = ROOT / "backend" / "scripts" / "export_openapi.py"


class OpenApiSchemaTest(unittest.TestCase):
    def test_openapi_schema_builds(self) -> None:
        schema = app.openapi()

        self.assertTrue(schema["openapi"].startswith("3."))
        self.assertEqual(schema["info"]["title"], "Photo Manager API")
        self.assertIn("/api/v1/assets/", schema["paths"])

    def test_committed_openapi_schema_is_up_to_date(self) -> None:
        result = subprocess.run(
            [sys.executable, str(EXPORT_SCRIPT), "--check"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_committed_openapi_schema_is_valid_json(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

        self.assertTrue(schema["openapi"].startswith("3."))
        self.assertIn("paths", schema)


if __name__ == "__main__":
    unittest.main()
