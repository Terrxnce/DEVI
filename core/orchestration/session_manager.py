import json
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Dict, List, Optional, Tuple


@dataclass
class SessionWindow:
    name: str
    start: time
    end: time
    max_trades_per_hour: int
    score_bonus: float


class SessionManager:
    def __init__(self, sessions_path: str, system_path: str):
        self.sessions_path = sessions_path
        self.system_path = system_path
        self.windows: List[SessionWindow] = []
        self.timezone = timezone.utc
        self.autonomy: Dict = {}
        self.symbols: List[str] = []
        self._current_session: Optional[str] = None
        self._paused_until_ts: Optional[datetime] = None
        self.reset_session_counters()
        self._load_configs()

    def _load_configs(self) -> None:
        with open(self.sessions_path, "r", encoding="utf-8") as f:
            sess = json.load(f)
        self.timezone = timezone.utc if sess.get("timezone", "UTC").upper() == "UTC" else timezone.utc
        self.windows = []
        for w in sess.get("windows", []):
            start_h, start_m = map(int, w.get("start", "00:00").split(":"))
            end_h, end_m = map(int, w.get("end", "00:00").split(":"))
            self.windows.append(
                SessionWindow(
                    name=w.get("name", "UNKNOWN"),
                    start=time(start_h, start_m, tzinfo=self.timezone),
                    end=time(end_h, end_m, tzinfo=self.timezone),
                    max_trades_per_hour=int(w.get("max_trades_per_hour", 1)),
                    score_bonus=float(w.get("score_bonus", 0.0)),
                )
            )
        with open(self.system_path, "r", encoding="utf-8") as f:
            syscfg = json.load(f)
        self.autonomy = syscfg.get("autonomy", {})
        self.symbols = syscfg.get("symbols", [])

    def get_active_session(self, ts: datetime) -> Optional[str]:
        ts_utc = ts.astimezone(timezone.utc)
        t = ts_utc.timetz()
        for w in self.windows:
            if w.start <= t <= w.end:
                return w.name
        return None

    def update_and_rotate(self, ts: datetime) -> Tuple[Optional[str], Optional[str]]:
        prev = self._current_session
        cur = self.get_active_session(ts)
        if cur != prev:
            self._current_session = cur
            self.reset_session_counters()
            return prev, cur
        return prev, None

    def reset_session_counters(self) -> None:
        self.session_counters = {
            "full_sl_hits": 0,
            "decisions_attempted": 0,
            "decisions_accepted": 0,
        }

    @property
    def current_session(self) -> Optional[str]:
        return self._current_session

    @property
    def tracked_symbols(self) -> List[str]:
        return list(self.symbols)
