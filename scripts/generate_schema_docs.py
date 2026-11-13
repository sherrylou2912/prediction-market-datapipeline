"""Regenerate the marked schema tables from the authoritative JSON registry."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- BEGIN GENERATED SCHEMA TABLES -->"
END = "<!-- END GENERATED SCHEMA TABLES -->"


def generated_tables(registry: dict) -> str:
    # Imported here so main() can first put the project root on sys.path.
    from src.data_schema.contracts import RULE_FIELDS

    lines = [START]
    for dataset, contract in registry["datasets"].items():
        lines += [
            "",
            f"### `{dataset}`",
            "",
            "| 字段 | 类型 | 可空 | 主键 | 适用规则 | 说明 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for field, spec in contract["fields"].items():
            rules = [
                json.dumps(rule, ensure_ascii=False, sort_keys=True)
                for rule in contract["rules"]
                if field in (rule[key] for key in RULE_FIELDS[rule["type"]])
            ]
            rule_text = "<br>".join(f"`{rule}`" for rule in rules) or "—"
            lines.append(
                f"| `{field}` | `{spec['type'].rstrip('?')}` | {'是' if spec['type'].endswith('?') else '否'} | {'是' if field in contract['primary_key'] else '否'} | {rule_text} | {spec['description'].replace('|', '&#124;')} |"
            )
    return "\n".join(lines + ["", END])


def regenerate(document: str, registry: dict) -> str:
    if document.count(START) != 1 or document.count(END) != 1:
        raise ValueError("schema document must contain one pair of generation markers")
    before, rest = document.split(START, 1)
    _, after = rest.split(END, 1)
    return before + generated_tables(registry) + after


def main() -> None:
    if len(sys.argv) > 1:
        sys.exit("usage: python scripts/generate_schema_docs.py (takes no arguments; rewrites docs/SCHEMAS.md)")
    # Direct invocation sets sys.path[0] to scripts/, not the project root.
    sys.path.insert(0, str(ROOT))
    from src.data_schema.contracts import load_registry

    path = ROOT / "docs/SCHEMAS.md"
    registry = load_registry(ROOT / "src/data_schema/schema_registry.json")
    path.write_text(regenerate(path.read_text(encoding="utf-8"), registry), encoding="utf-8")


if __name__ == "__main__":
    main()
