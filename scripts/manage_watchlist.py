"""watchlist.json 관리 CLI.

workflow_dispatch에서 호출되거나 로컬에서 직접 실행 가능.

사용 예:
    python scripts/manage_watchlist.py add --query "거북이 720" --label "거북이 720 시리즈"
    python scripts/manage_watchlist.py remove --query "거북이 720"
    python scripts/manage_watchlist.py toggle --query "거북이 720"

설계:
- 입력 query는 whitespace 정규화 (앞뒤 trim + 연속 공백 → 단일 공백) 후 매칭.
  watchlist에 저장될 때도 정규화된 형태로 저장 → 검색 시 일관성 보장.
- add: 이미 존재하면 active=true로 reactivate + label/note 갱신.
  완전히 새 entry면 append.
- remove: 항목 자체 삭제. 일시 중지가 목적이면 toggle 사용 권장.
- toggle: active를 반전 (true ↔ false).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional


def normalize_query(q: str) -> str:
    """앞뒤 공백 제거 + 연속 공백 단일화."""
    return " ".join(q.split())


def load_watchlist(path: Path) -> dict:
    if not path.exists():
        return {"queries": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_watchlist(path: Path, data: dict) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")


def find_index(data: dict, normalized_query: str) -> Optional[int]:
    for i, entry in enumerate(data.get("queries", [])):
        if normalize_query(entry.get("query", "")) == normalized_query:
            return i
    return None


def action_add(data: dict, query: str, label: str, note: str) -> str:
    nq = normalize_query(query)
    if not nq:
        raise ValueError("query is empty after normalization")

    idx = find_index(data, nq)
    if idx is not None:
        entry = data["queries"][idx]
        previously_active = entry.get("active", True)
        entry["active"] = True
        if label.strip():
            entry["label"] = label.strip()
        if note.strip():
            entry["note"] = note.strip()
        suffix = "" if previously_active else " (reactivated)"
        return f"updated existing entry: {nq!r}{suffix}"

    data.setdefault("queries", []).append(
        {
            "query": nq,
            "label": label.strip() or nq,
            "active": True,
            "note": note.strip(),
        }
    )
    return f"added new entry: {nq!r}"


def action_remove(data: dict, query: str) -> str:
    nq = normalize_query(query)
    idx = find_index(data, nq)
    if idx is None:
        raise ValueError(f"entry not found: {nq!r}")
    removed = data["queries"].pop(idx)
    return f"removed: {removed.get('query')!r}"


def action_toggle(data: dict, query: str) -> str:
    nq = normalize_query(query)
    idx = find_index(data, nq)
    if idx is None:
        raise ValueError(f"entry not found: {nq!r}")
    entry = data["queries"][idx]
    entry["active"] = not entry.get("active", True)
    state = "active" if entry["active"] else "inactive"
    return f"toggled {nq!r} → {state}"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="manage watchlist.json")
    p.add_argument("action", choices=["add", "remove", "toggle"])
    p.add_argument("--query", required=True, help="search query string")
    p.add_argument("--label", default="", help="display label (used in 'add')")
    p.add_argument("--note", default="", help="optional note (used in 'add')")
    p.add_argument(
        "--watchlist",
        type=Path,
        default=Path("watchlist.json"),
        help="path to watchlist.json (default: ./watchlist.json)",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    data = load_watchlist(args.watchlist)

    try:
        if args.action == "add":
            msg = action_add(data, args.query, args.label, args.note)
        elif args.action == "remove":
            msg = action_remove(data, args.query)
        elif args.action == "toggle":
            msg = action_toggle(data, args.query)
        else:
            raise ValueError(f"unknown action: {args.action}")
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1

    save_watchlist(args.watchlist, data)
    print(f"[ok] {msg}")
    print(f"[ok] watchlist now has {len(data.get('queries', []))} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
