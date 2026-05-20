from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def _result(label: str):
    return SimpleNamespace(
        prediction=SimpleNamespace(output=SimpleNamespace(label=label)),
    )


class Magika:
    def identify_path(self, path):
        p = Path(path)
        if p.suffix.lower() == ".pdf":
            return _result("pdf")
        return _result("txt")

    def identify_bytes(self, data: bytes):
        if data[:4] == b"%PDF":
            return _result("pdf")
        return _result("txt")
