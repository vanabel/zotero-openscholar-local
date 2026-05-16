#!/usr/bin/env python3
"""从本地 data/parsed 摘录生成 P0 fixture（开发机有解析产物时运行）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

ROOT = API_ROOT / "tests" / "fixtures" / "papers"
PARSED = API_ROOT / "data" / "parsed"


def write_fixture(fid: str, md: str, meta: dict) -> None:
    d = ROOT / fid
    d.mkdir(parents=True, exist_ok=True)
    (d / "document.md").write_text(md.strip() + "\n", encoding="utf-8")
    (d / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def excerpt(src: Path, start: int, end: int) -> str:
    lines = src.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[start:end])


def main() -> None:
    if not PARSED.is_dir():
        print(f"跳过：无 {PARSED}，保留仓库内已有 fixture", file=sys.stderr)
        return

    write_fixture(
        "fixture-en-math-01",
        excerpt(PARSED / "02ae50a93c54fab97c86a09c3b8a037b/document.md", 0, 120),
        {
            "id": "fixture-en-math-01",
            "kind": "en-math-formulas",
            "source": "excerpt: Andrews multi-point maximum principles",
            "min_chunks": 2,
            "section_paths_contain": ["Introductory"],
            "fts": [{"query": "multi-point maximum principle", "min_hits": 1, "body_contains": "maximum"}],
        },
    )
    write_fixture(
        "fixture-en-math-02",
        excerpt(PARSED / "92cddb35d4988d816d3279fad43ee450/document.md", 0, 150),
        {
            "id": "fixture-en-math-02",
            "kind": "en-math-theorems",
            "source": "excerpt: Grigor'yan integral maximum principle",
            "min_chunks": 3,
            "section_paths_contain": ["Introduction"],
            "text_must_include": ["Theorem 1", "integral maximum principle"],
            "fts": [{"query": "heat kernel Dirichlet", "min_hits": 1, "body_contains": "heat"}],
        },
    )
    write_fixture(
        "fixture-en-math-03",
        excerpt(PARSED / "e7bde2df966ad91731afb8c20c9f15da/document.md", 0, 80),
        {
            "id": "fixture-en-math-03",
            "kind": "en-math-standard",
            "source": "excerpt: Lu & Sleeman parabolic systems",
            "min_chunks": 2,
            "section_paths_contain": ["Synopsis"],
            "fts": [{"query": "semilinear parabolic comparison theorem", "min_hits": 1, "body_contains": "parabolic"}],
        },
    )
    write_fixture(
        "fixture-scan-01",
        excerpt(PARSED / "fc2576ecc0977a23489b4dcebda11d70/document.md", 0, 25)
        + "\n\n"
        + excerpt(PARSED / "fc2576ecc0977a23489b4dcebda11d70/document.md", 380, 520),
        {
            "id": "fixture-scan-01",
            "kind": "scan-ocr-pages",
            "source": "excerpt: Maximum Entropy book (Page markers)",
            "min_chunks": 2,
            "text_must_include": ["## Page", "Table 1"],
            "fts": [{"query": "Levy-Khinchin MassInf", "min_hits": 1, "body_contains": "MassInf"}],
        },
    )
    write_fixture(
        "fixture-table-01",
        excerpt(PARSED / "fc2576ecc0977a23489b4dcebda11d70/document.md", 383, 530),
        {
            "id": "fixture-table-01",
            "kind": "tables-figures",
            "source": "excerpt: Table 1 and Figure 1 captions",
            "min_chunks": 2,
            "text_must_include": ["Table 1", "Figure 1"],
            "fts": [{"query": "Table 1 Levy-Khinchin", "min_hits": 1, "body_contains": "Table"}],
        },
    )

    manifest = []
    for p in sorted(ROOT.iterdir()):
        if p.is_dir() and (p / "metadata.json").is_file():
            manifest.append(json.loads((p / "metadata.json").read_text(encoding="utf-8")))
    (ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已更新 {len(manifest)} 个英文/扫描 fixture（中文 synthetic 未覆盖）")


if __name__ == "__main__":
    main()
