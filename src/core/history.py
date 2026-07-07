"""
Download history persistence and analytics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any, Iterable

from src.utils.paths import get_history_path


@dataclass
class HistoryEntry:
    job_id: str
    title: str
    artist: str
    album: str
    platform: str
    source_url: str
    output_path: str
    output_format: str
    status: str
    tags: list[str]
    size_bytes: int
    checksum_sha256: str
    started_at: str
    finished_at: str
    duration_s: float
    avg_speed_bps: float
    error_message: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HistoryEntry":
        return cls(
            job_id=data.get("job_id", ""),
            title=data.get("title", ""),
            artist=data.get("artist", ""),
            album=data.get("album", ""),
            platform=data.get("platform", ""),
            source_url=data.get("source_url", ""),
            output_path=data.get("output_path", ""),
            output_format=data.get("output_format", ""),
            status=data.get("status", ""),
            tags=list(data.get("tags", []) or []),
            size_bytes=int(data.get("size_bytes", 0) or 0),
            checksum_sha256=data.get("checksum_sha256", ""),
            started_at=data.get("started_at", ""),
            finished_at=data.get("finished_at", ""),
            duration_s=float(data.get("duration_s", 0.0) or 0.0),
            avg_speed_bps=float(data.get("avg_speed_bps", 0.0) or 0.0),
            error_message=data.get("error_message", ""),
        )


class HistoryStore:
    def __init__(self):
        self._path = get_history_path()
        self._entries: list[HistoryEntry] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._entries = []
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._entries = [HistoryEntry.from_dict(e) for e in raw]
        except Exception:
            self._entries = []

    def _save(self) -> None:
        data = [asdict(e) for e in self._entries]
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add_entry(self, entry: HistoryEntry) -> None:
        self._entries.append(entry)
        self._save()

    def list_entries(self) -> list[HistoryEntry]:
        return list(self._entries)

    def search(
        self,
        query: str = "",
        status: str = "",
        platform: str = "",
    ) -> list[HistoryEntry]:
        query = (query or "").lower().strip()
        results: Iterable[HistoryEntry] = self._entries

        if status:
            results = [e for e in results if e.status.lower() == status.lower()]
        if platform:
            results = [e for e in results if e.platform.lower() == platform.lower()]
        if not query:
            return list(results)

        def _matches(e: HistoryEntry) -> bool:
            haystack = " ".join([
                e.title, e.artist, e.album, e.source_url, " ".join(e.tags), e.output_path,
            ]).lower()
            return query in haystack

        return [e for e in results if _matches(e)]

    def stats(self) -> dict[str, Any]:
        total = len(self._entries)
        if total == 0:
            return {
                "total": 0,
                "success": 0,
                "failed": 0,
                "success_rate": 0.0,
                "bytes": 0,
                "avg_speed_bps": 0.0,
            }
        success = sum(1 for e in self._entries if e.status.lower() == "done")
        failed = sum(1 for e in self._entries if e.status.lower() == "failed")
        bytes_total = sum(e.size_bytes for e in self._entries)
        avg_speed = sum(e.avg_speed_bps for e in self._entries if e.avg_speed_bps > 0)
        avg_speed = avg_speed / max(1, sum(1 for e in self._entries if e.avg_speed_bps > 0))
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "success_rate": round((success / total) * 100, 1),
            "bytes": bytes_total,
            "avg_speed_bps": avg_speed,
        }

    def export_json(self, path: str) -> None:
        data = [asdict(e) for e in self._entries]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def export_csv(self, path: str) -> None:
        import csv
        fields = list(HistoryEntry("", "", "", "", "", "", "", "", "", [], 0, "", "", "", 0.0, 0.0).__dict__.keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for e in self._entries:
                writer.writerow(asdict(e))
