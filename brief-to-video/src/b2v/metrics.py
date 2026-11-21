"""SQLite run log: tracks attempts, approval, and cost per approved post."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import PostResult


class Metrics:
    def __init__(self, db_path: Path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path))
        self.db.execute("""CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, brief_id TEXT, approved INTEGER,
            attempts INTEGER, cost_usd REAL, issues TEXT, video_path TEXT)""")

    def record(self, r: PostResult) -> None:
        self.db.execute("INSERT INTO runs (ts, brief_id, approved, attempts, cost_usd, issues, video_path)"
                        " VALUES (?,?,?,?,?,?,?)",
                        (datetime.now(timezone.utc).isoformat(), r.brief_id, int(r.approved), r.attempts,
                         r.cost_usd, "; ".join(r.issues), r.video_path))
        self.db.commit()

    def summary(self) -> dict:
        runs, approved, cost = self.db.execute(
            "SELECT COUNT(*), COALESCE(SUM(approved),0), COALESCE(SUM(cost_usd),0) FROM runs").fetchone()
        return {"runs": runs, "approved": approved, "total_cost_usd": round(cost, 6),
                "cost_per_approved_post_usd": round(cost / approved, 6) if approved else None,
                "approval_rate": round(approved / runs, 3) if runs else None}
