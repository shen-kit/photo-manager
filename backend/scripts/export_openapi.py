#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
DEFAULT_OUTPUT = BACKEND_DIR / "openapi-schema.json"


def _load_schema() -> dict[str, Any]:
    sys.path.insert(0, str(BACKEND_DIR))
    from app.main import app

    return app.openapi()


def _render_schema(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export FastAPI OpenAPI schema.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Schema output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if output file is missing or not up to date.",
    )
    args = parser.parse_args()

    try:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        rendered = _render_schema(_load_schema())
        if args.check:
            if not output.exists():
                print(f"OpenAPI schema missing: {output}", file=sys.stderr)
                return 1
            current = output.read_text(encoding="utf-8")
            if current != rendered:
                print(
                    f"OpenAPI schema out of date: {output}\n"
                    "Run `just openapi` to regenerate it.",
                    file=sys.stderr,
                )
                return 1
            print(f"OpenAPI schema up to date: {output}")
            return 0

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"Wrote OpenAPI schema to {output}")
        return 0
    except Exception as exc:  # noqa: BLE001 - script must fail loudly in CI
        print(f"Failed to export OpenAPI schema: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
