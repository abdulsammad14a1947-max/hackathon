"""Repair single-level UTF-8 -> cp1252 mojibake introduced by ANSI-mode file rewrites.

Strategy: only sequences that START with the cp1252 bytes 0xC2 ('Â') or 0xE2 ('â')
are candidates. We collect their cp1252 bytes (plus following candidate chars) and
attempt a strict UTF-8 decode of 2-3 bytes. If it succeeds we substitute the decoded
character; otherwise the text is left untouched. Genuine non-ASCII characters that
are not part of a valid byte sequence are preserved.

Usage: python .tools/fix_mojibake.py [--dry-run] [root ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

# unicode char -> cp1252 byte (reverse of the cp1252 codec table)
_CP1252 = {
    0x80: "€", 0x82: "‚", 0x83: "ƒ", 0x84: "„", 0x85: "…",
    0x86: "†", 0x87: "‡", 0x88: "ˆ", 0x89: "‰", 0x8A: "Š",
    0x8B: "‹", 0x8C: "Œ", 0x8E: "Ž", 0x91: "‘", 0x92: "’",
    0x93: "“", 0x94: "”", 0x95: "•", 0x96: "–", 0x97: "—",
    0x98: "˜", 0x99: "™", 0x9A: "š", 0x9B: "›", 0x9C: "œ",
    0x9E: "ž", 0x9F: "Ÿ",
}
for b in range(0xA0, 0x100):
    _CP1252[b] = chr(b)
_CHAR_TO_BYTE = {v: k for k, v in _CP1252.items()}
# the two bytes that can begin a mojibake cluster
_START = {"Â", "â"}


def _try_repair(text: str) -> tuple[str, int]:
    out: list[str] = []
    i = 0
    fixed = 0
    n = len(text)
    while i < n:
        ch = text[i]
        # `ch` always gets consumed; repair only substitutes it when the bytes
        # it (plus its followers) encode actually decode as multi-byte UTF-8.
        replacement: str | None = None
        matched = 1
        if ch in _START and ch in _CHAR_TO_BYTE:
            for size in (3, 2):
                chunk = text[i : i + size]
                if len(chunk) < size:
                    continue
                try:
                    b = bytes(_CHAR_TO_BYTE[c] for c in chunk)
                except KeyError:
                    continue
                try:
                    decoded = b.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                # only accept real multi-byte substitutions, never ASCII output
                if decoded.isascii() or len(decoded) != 1:
                    continue
                replacement = decoded
                matched = size
                break
        if replacement is None:
            out.append(ch)
            i += 1
        else:
            out.append(replacement)
            i += matched
            fixed += 1
    return "".join(out), fixed


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    roots = [Path(a) for a in args] or [
        Path(__file__).resolve().parent.parent / "frontend",
        Path(__file__).resolve().parent.parent / "backend",
        Path(__file__).resolve().parent.parent / "docs",
        Path(__file__).resolve().parent.parent,
    ]
    exts = {".py", ".ts", ".tsx", ".css", ".md", ".json", ".txt", ".html"}
    skip_dirs = {"node_modules", ".next", ".pglocal", "__pycache__", ".mypy_cache", ".pytest_cache", ".playwright-mcp", ".venv", "venv", "site-packages", ".git", ".cache", "dist", "build", "coverage"}
    seen: set[Path] = set()
    total_files = 0

    def walk(root: Path) -> list[Path]:
        if root.is_file():
            return [root]
        out: list[Path] = []
        stack = [root]
        while stack:
            d = stack.pop()
            try:
                for child in d.iterdir():
                    if child.is_dir():
                        if child.name not in skip_dirs:
                            stack.append(child)
                    elif child.is_file() and child.suffix.lower() in exts:
                        out.append(child)
            except OSError:
                continue
        return out

    for root in roots:
        for p in walk(root):
            if p in seen or p == Path(__file__):
                continue
            seen.add(p)
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            repaired, count = _try_repair(text)
            if count and repaired != text:
                total_files += 1
                print(f"{'DRY ' if dry else 'FIXED'} {count:3d} clusters  {p}")
                if not dry:
                    p.write_text(repaired, encoding="utf-8", newline="")
    print(f"{'Would fix' if dry else 'Fixed'} {total_files} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
