"""scripts/manage_watchlist.py 회귀 테스트."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# scripts 디렉토리를 path에 추가 (패키지가 아니므로 직접 import)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import manage_watchlist as mw  # noqa: E402


def _write_watchlist(path: Path, queries: list[dict]) -> None:
    path.write_text(
        json.dumps({"queries": queries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_watchlist(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestNormalizeQuery(unittest.TestCase):
    def test_collapses_multiple_spaces(self) -> None:
        self.assertEqual(mw.normalize_query("거북이   720"), "거북이 720")

    def test_strips_leading_trailing(self) -> None:
        self.assertEqual(mw.normalize_query("  거북이 720  "), "거북이 720")

    def test_empty_becomes_empty(self) -> None:
        self.assertEqual(mw.normalize_query("   "), "")


class TestActionAdd(unittest.TestCase):
    def test_adds_new_entry(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wl.json"
            _write_watchlist(path, [])
            rc = mw.main(["add", "--query", "거북이 720", "--watchlist", str(path)])
            self.assertEqual(rc, 0)
            data = _read_watchlist(path)
            self.assertEqual(len(data["queries"]), 1)
            self.assertEqual(data["queries"][0]["query"], "거북이 720")
            self.assertEqual(data["queries"][0]["label"], "거북이 720")  # default
            self.assertTrue(data["queries"][0]["active"])

    def test_uses_label_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wl.json"
            _write_watchlist(path, [])
            mw.main(
                [
                    "add",
                    "--query", "거북이 720",
                    "--label", "신슈키레이 거북이 720ml 시리즈",
                    "--note", "재입고 감시",
                    "--watchlist", str(path),
                ]
            )
            data = _read_watchlist(path)
            self.assertEqual(data["queries"][0]["label"], "신슈키레이 거북이 720ml 시리즈")
            self.assertEqual(data["queries"][0]["note"], "재입고 감시")

    def test_reactivates_inactive_entry(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wl.json"
            _write_watchlist(
                path,
                [{"query": "거북이 720", "label": "old", "active": False, "note": ""}],
            )
            rc = mw.main(["add", "--query", "거북이 720", "--watchlist", str(path)])
            self.assertEqual(rc, 0)
            data = _read_watchlist(path)
            self.assertEqual(len(data["queries"]), 1)  # 중복 안 만들고 기존 entry 갱신
            self.assertTrue(data["queries"][0]["active"])
            self.assertEqual(data["queries"][0]["label"], "old")  # label 비어 있으면 유지

    def test_normalizes_whitespace_in_query(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wl.json"
            _write_watchlist(path, [])
            mw.main(["add", "--query", "  거북이   720  ", "--watchlist", str(path)])
            data = _read_watchlist(path)
            self.assertEqual(data["queries"][0]["query"], "거북이 720")

    def test_duplicate_detection_uses_normalization(self) -> None:
        """'거북이 720'과 '거북이  720'은 같은 entry로 취급."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wl.json"
            _write_watchlist(
                path, [{"query": "거북이 720", "label": "x", "active": True}]
            )
            mw.main(["add", "--query", "거북이  720", "--watchlist", str(path)])
            data = _read_watchlist(path)
            self.assertEqual(len(data["queries"]), 1)

    def test_empty_query_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wl.json"
            _write_watchlist(path, [])
            rc = mw.main(["add", "--query", "   ", "--watchlist", str(path)])
            self.assertEqual(rc, 1)


class TestActionRemove(unittest.TestCase):
    def test_removes_existing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wl.json"
            _write_watchlist(
                path,
                [
                    {"query": "거북이 720", "label": "a", "active": True},
                    {"query": "우부스나 카바 4농", "label": "b", "active": True},
                ],
            )
            rc = mw.main(["remove", "--query", "거북이 720", "--watchlist", str(path)])
            self.assertEqual(rc, 0)
            data = _read_watchlist(path)
            self.assertEqual(len(data["queries"]), 1)
            self.assertEqual(data["queries"][0]["query"], "우부스나 카바 4농")

    def test_not_found_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wl.json"
            _write_watchlist(path, [])
            rc = mw.main(["remove", "--query", "거북이 720", "--watchlist", str(path)])
            self.assertEqual(rc, 1)


class TestActionToggle(unittest.TestCase):
    def test_active_to_inactive(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wl.json"
            _write_watchlist(
                path, [{"query": "거북이 720", "label": "x", "active": True}]
            )
            rc = mw.main(["toggle", "--query", "거북이 720", "--watchlist", str(path)])
            self.assertEqual(rc, 0)
            data = _read_watchlist(path)
            self.assertFalse(data["queries"][0]["active"])

    def test_inactive_to_active(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wl.json"
            _write_watchlist(
                path, [{"query": "거북이 720", "label": "x", "active": False}]
            )
            mw.main(["toggle", "--query", "거북이 720", "--watchlist", str(path)])
            data = _read_watchlist(path)
            self.assertTrue(data["queries"][0]["active"])

    def test_toggle_not_found_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wl.json"
            _write_watchlist(path, [])
            rc = mw.main(["toggle", "--query", "거북이 720", "--watchlist", str(path)])
            self.assertEqual(rc, 1)


class TestFilePersistence(unittest.TestCase):
    def test_preserves_korean_japanese_in_file(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wl.json"
            _write_watchlist(path, [])
            mw.main(
                [
                    "add",
                    "--query", "나베시마 키타시즈쿠 1.8",
                    "--label", "鍋島 キタシズク",
                    "--watchlist", str(path),
                ]
            )
            raw = path.read_text(encoding="utf-8")
            self.assertIn("나베시마", raw)
            self.assertIn("鍋島", raw)
            self.assertNotIn("\\u", raw)  # ascii escape 안 됨


if __name__ == "__main__":
    unittest.main()
