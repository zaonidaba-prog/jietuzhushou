from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class ClipboardItem:
    id: int
    kind: str
    text: str
    preview: str
    image_path: str
    file_paths: list[str]
    created_at: str
    pinned: bool
    content_hash: str = ""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class HistoryDB:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS clipboard_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                text TEXT NOT NULL DEFAULT '',
                preview TEXT NOT NULL DEFAULT '',
                image_path TEXT NOT NULL DEFAULT '',
                file_paths TEXT NOT NULL DEFAULT '[]',
                content_hash TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_clip_created ON clipboard_items(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_clip_kind ON clipboard_items(kind);
            CREATE INDEX IF NOT EXISTS idx_clip_pinned ON clipboard_items(pinned);
            """
        )
        self.conn.commit()

    # ------------------------------------------------------------------ write
    def add_item(
        self,
        kind: str,
        text: str = "",
        preview: str = "",
        image_path: str = "",
        file_paths: list[str] | None = None,
        content_hash: str = "",
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO clipboard_items
                (kind, text, preview, image_path, file_paths, content_hash, created_at, pinned)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                kind,
                text,
                preview,
                image_path,
                json.dumps(file_paths or [], ensure_ascii=False),
                content_hash,
                _now(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def set_pinned(self, item_id: int, pinned: bool) -> None:
        self.conn.execute(
            "UPDATE clipboard_items SET pinned=? WHERE id=?",
            (1 if pinned else 0, item_id),
        )
        self.conn.commit()

    def delete_item(self, item_id: int) -> str | None:
        row = self.conn.execute(
            "SELECT image_path FROM clipboard_items WHERE id=?", (item_id,)
        ).fetchone()
        self.conn.execute("DELETE FROM clipboard_items WHERE id=?", (item_id,))
        self.conn.commit()
        return row["image_path"] if row else None

    def clear_all(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT image_path FROM clipboard_items WHERE image_path != ''"
        ).fetchall()
        self.conn.execute("DELETE FROM clipboard_items")
        self.conn.commit()
        return [r["image_path"] for r in rows]

    # ------------------------------------------------------------------- read
    def _where(self, filter_kind: str, search: str) -> tuple[str, list]:
        clauses: list[str] = []
        params: list = []
        if filter_kind in ("text", "image", "file"):
            clauses.append("kind = ?")
            params.append(filter_kind)
        elif filter_kind == "pinned":
            clauses.append("pinned = 1")

        if search.strip():
            like = f"%{_escape_like(search.strip())}%"
            clauses.append(
                "(text LIKE ? ESCAPE '\\' OR preview LIKE ? ESCAPE '\\' "
                "OR file_paths LIKE ? ESCAPE '\\')"
            )
            params.extend([like, like, like])

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    def list_items(
        self,
        filter_kind: str = "all",
        search: str = "",
        limit: int = 200,
        offset: int = 0,
    ) -> list[ClipboardItem]:
        where, params = self._where(filter_kind, search)
        rows = self.conn.execute(
            f"""
            SELECT * FROM clipboard_items
            {where}
            ORDER BY pinned DESC, created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def count_items(self, filter_kind: str = "all", search: str = "") -> int:
        where, params = self._where(filter_kind, search)
        row = self.conn.execute(
            f"SELECT COUNT(*) AS n FROM clipboard_items {where}", params
        ).fetchone()
        return int(row["n"]) if row else 0

    def get_item(self, item_id: int) -> ClipboardItem | None:
        row = self.conn.execute(
            "SELECT * FROM clipboard_items WHERE id=?", (item_id,)
        ).fetchone()
        return self._row_to_item(row) if row else None

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> ClipboardItem:
        try:
            files = json.loads(row["file_paths"] or "[]")
        except Exception:
            files = []
        return ClipboardItem(
            id=int(row["id"]),
            kind=row["kind"],
            text=row["text"] or "",
            preview=row["preview"] or "",
            image_path=row["image_path"] or "",
            file_paths=files,
            created_at=row["created_at"],
            pinned=bool(row["pinned"]),
            content_hash=row["content_hash"] or "",
        )

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass
