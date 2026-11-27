"""Reads Claude Code JSONL transcripts and extracts token usage."""

import json
import os
import glob
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass


WINDOW_HOURS = 4


@dataclass
class TokenEntry:
    timestamp: datetime
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    cost_usd: float
    session_id: str

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_creation_tokens

    @property
    def effective_tokens(self) -> int:
        """Tokens that count against rate limit (excludes cache reads)."""
        return self.input_tokens + self.output_tokens + self.cache_creation_tokens


@dataclass
class WindowStats:
    entries: list
    total_input: int
    total_output: int
    total_cache_creation: int
    total_cache_read: int
    total_cost: float
    window_start: datetime
    window_end: datetime
    oldest_entry_time: datetime | None
    next_expiry: datetime | None

    @property
    def effective_tokens(self) -> int:
        return self.total_input + self.total_output + self.total_cache_creation

    @property
    def time_until_next_expiry(self) -> timedelta | None:
        if self.oldest_entry_time is None:
            return None
        expires_at = self.oldest_entry_time + timedelta(hours=WINDOW_HOURS)
        now = datetime.now(timezone.utc)
        remaining = expires_at - now
        return remaining if remaining.total_seconds() > 0 else timedelta(0)

    @property
    def window_reset_time(self) -> datetime | None:
        if self.oldest_entry_time is None:
            return None
        return self.oldest_entry_time + timedelta(hours=WINDOW_HOURS)


def get_projects_dir() -> str:
    return os.path.expanduser("~/.claude/projects")


def collect_window_stats(limit_tokens: int = 200_000) -> WindowStats:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=WINDOW_HOURS)

    entries = []
    projects_dir = get_projects_dir()

    if not os.path.exists(projects_dir):
        return _empty_stats(now, window_start)

    jsonl_files = glob.glob(os.path.join(projects_dir, "**/*.jsonl"), recursive=True)

    for filepath in jsonl_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if data.get("type") != "assistant":
                        continue

                    msg = data.get("message", {})
                    usage = msg.get("usage", {})
                    if not usage:
                        continue

                    ts_str = data.get("timestamp", "")
                    if not ts_str:
                        continue

                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except ValueError:
                        continue

                    if ts < window_start:
                        continue

                    session_id = os.path.basename(filepath).replace(".jsonl", "")

                    entries.append(TokenEntry(
                        timestamp=ts,
                        input_tokens=usage.get("input_tokens", 0),
                        output_tokens=usage.get("output_tokens", 0),
                        cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
                        cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                        cost_usd=data.get("costUSD", 0.0) or 0.0,
                        session_id=session_id,
                    ))
        except (OSError, IOError):
            continue

    entries.sort(key=lambda e: e.timestamp)

    if not entries:
        return _empty_stats(now, window_start)

    return WindowStats(
        entries=entries,
        total_input=sum(e.input_tokens for e in entries),
        total_output=sum(e.output_tokens for e in entries),
        total_cache_creation=sum(e.cache_creation_tokens for e in entries),
        total_cache_read=sum(e.cache_read_tokens for e in entries),
        total_cost=sum(e.cost_usd for e in entries),
        window_start=window_start,
        window_end=now,
        oldest_entry_time=entries[0].timestamp if entries else None,
        next_expiry=entries[0].timestamp + timedelta(hours=WINDOW_HOURS) if entries else None,
    )


def get_hourly_buckets(entries: list, hours: int = 4) -> list[tuple[datetime, int]]:
    """Returns token counts per 15-minute bucket over the last N hours."""
    now = datetime.now(timezone.utc)
    buckets = {}
    for i in range(hours * 4):
        bucket_start = now - timedelta(minutes=15 * (hours * 4 - i))
        buckets[i] = {"start": bucket_start, "tokens": 0}

    for entry in entries:
        for i, bucket in buckets.items():
            bucket_end = bucket["start"] + timedelta(minutes=15)
            if bucket["start"] <= entry.timestamp < bucket_end:
                buckets[i]["tokens"] += entry.effective_tokens
                break

    return [(b["start"], b["tokens"]) for b in buckets.values()]


def get_cost_history() -> dict:
    """Returns cost history grouped by local date."""
    projects_dir = get_projects_dir()
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    seven_days_ago = today - timedelta(days=7)

    daily: dict = {}

    if os.path.exists(projects_dir):
        jsonl_files = glob.glob(os.path.join(projects_dir, "**/*.jsonl"), recursive=True)
        for filepath in jsonl_files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if data.get("type") != "assistant":
                            continue
                        cost = data.get("costUSD", 0.0) or 0.0
                        if cost == 0.0:
                            continue
                        ts_str = data.get("timestamp", "")
                        if not ts_str:
                            continue
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        except ValueError:
                            continue
                        local_date = ts.astimezone().date()
                        if local_date < seven_days_ago:
                            continue
                        daily[local_date] = daily.get(local_date, 0.0) + cost
            except (OSError, IOError):
                continue

    today_cost = daily.get(today, 0.0)
    yesterday_cost = daily.get(yesterday, 0.0)
    week_cost = sum(daily.values())

    day_names = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    daily_list = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        name = day_names[d.weekday()]
        daily_list.append((name, daily.get(d, 0.0)))

    return {
        "today": today_cost,
        "yesterday": yesterday_cost,
        "week": week_cost,
        "daily": daily_list,
    }


def _empty_stats(now: datetime, window_start: datetime) -> WindowStats:
    return WindowStats(
        entries=[],
        total_input=0,
        total_output=0,
        total_cache_creation=0,
        total_cache_read=0,
        total_cost=0.0,
        window_start=window_start,
        window_end=now,
        oldest_entry_time=None,
        next_expiry=None,
    )
