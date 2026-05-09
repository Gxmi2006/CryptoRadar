from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from app.learning.adaptive_scoring import AdaptiveScoringEngine


class LearningReport:
    def __init__(self, db: Any, config: dict[str, Any]):
        self.db = db
        self.config = config

    def render_text(self) -> str:
        rows = self.db.query("SELECT * FROM signals")
        perf = self.db.query("SELECT * FROM signal_performance")
        perf_by_signal = {row["signal_id"]: row for row in perf}
        lines = ["CryptoRadar Learning Report", ""]
        lines.append(f"Total signals tracked: {len(rows)}")
        lines.append(f"BUY signal win rate: {self._win_rate(rows, 'BUY')}")
        lines.append(f"SELL signal win rate: {self._win_rate(rows, 'SELL')}")
        lines.append(f"HOLD accuracy: {self._win_rate(rows, 'HOLD')}")
        lines.append(f"HIGH_RISK warning accuracy: {self._win_rate(rows, 'HIGH_RISK')}")
        lines.append(f"Average move after BUY signals: {self._avg_move(rows, perf_by_signal, 'BUY')}")
        lines.append(f"Average move after SELL signals: {self._avg_move(rows, perf_by_signal, 'SELL')}")
        lines.append(f"Best-performing indicators: {self._indicator_note(rows, best=True)}")
        lines.append(f"Worst-performing indicators: {self._indicator_note(rows, best=False)}")
        lines.append(f"Best-performing symbols: {self._rank(rows, 'symbol', good=True)}")
        lines.append(f"Worst-performing symbols: {self._rank(rows, 'symbol', good=False)}")
        lines.append(f"Best-performing timeframes: {self._rank(rows, 'timeframe', good=True)}")
        lines.append(f"Worst-performing timeframes: {self._rank(rows, 'timeframe', good=False)}")
        lines.append("Best market conditions: tracked after more completed signals.")
        lines.append("Worst market conditions: tracked after more completed signals.")
        lines.append(f"Best knowledge sources: {self._source_rank(rows, good=True)}")
        lines.append(f"Weak knowledge sources: {self._source_rank(rows, good=False)}")
        lines.append("Suggested scoring weight changes:")
        for suggestion in AdaptiveScoringEngine(self.db, self.config).suggested_changes():
            lines.append(f"- {suggestion}")
        report = "\n".join(lines)
        self.db.execute(
            "INSERT INTO learning_reports(report_text, payload_json) VALUES (?, ?)",
            (report, self.db.dumps({"signals": len(rows)})),
        )
        return report

    def short_summary(self) -> str:
        rows = self.db.query("SELECT signal_type, final_result FROM signals")
        return f"Tracked signals={len(rows)}; BUY win rate={self._win_rate(rows, 'BUY')}; SELL win rate={self._win_rate(rows, 'SELL')}."

    @staticmethod
    def _win_rate(rows: list[dict[str, Any]], signal_type: str) -> str:
        subset = [row for row in rows if row.get("signal_type") == signal_type and row.get("final_result") in {"win", "loss"}]
        if not subset:
            return "unknown"
        wins = sum(1 for row in subset if row["final_result"] == "win")
        return f"{wins / len(subset):.1%} ({wins}/{len(subset)})"

    @staticmethod
    def _avg_move(rows: list[dict[str, Any]], perf: dict[str, dict[str, Any]], signal_type: str) -> str:
        moves = []
        for row in rows:
            if row.get("signal_type") != signal_type:
                continue
            data = perf.get(row["id"])
            if data and data.get("max_profit_pct") is not None:
                moves.append(float(data["max_profit_pct"]))
        return f"{mean(moves):.2f}%" if moves else "unknown"

    @staticmethod
    def _rank(rows: list[dict[str, Any]], key: str, good: bool) -> str:
        grouped: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            if row.get("final_result") in {"win", "loss"}:
                grouped[str(row.get(key) or "unknown")].append(row["final_result"])
        scored = []
        for name, results in grouped.items():
            if len(results) >= 2:
                wins = results.count("win")
                scored.append((wins / len(results), name))
        if not scored:
            return "unknown"
        scored.sort(reverse=good)
        return ", ".join(name for _, name in scored[:5])

    @staticmethod
    def _indicator_note(rows: list[dict[str, Any]], best: bool) -> str:
        counter = Counter()
        for row in rows:
            if row.get("final_result") != ("win" if best else "loss"):
                continue
            payload = row.get("payload_json") or "{}"
            try:
                import json

                data = json.loads(payload)
                reasons = data.get("score_details", {}).get("reasons", {})
                for reason_list in reasons.values():
                    counter.update(reason_list)
            except Exception:
                continue
        return ", ".join(item for item, _ in counter.most_common(5)) or "unknown"

    @staticmethod
    def _source_rank(rows: list[dict[str, Any]], good: bool) -> str:
        counter = Counter()
        target = "win" if good else "loss"
        for row in rows:
            if row.get("final_result") != target:
                continue
            try:
                import json

                data = json.loads(row.get("payload_json") or "{}")
                counter.update(data.get("knowledge_sources_used", []))
            except Exception:
                continue
        return ", ".join(item for item, _ in counter.most_common(5)) or "unknown"
