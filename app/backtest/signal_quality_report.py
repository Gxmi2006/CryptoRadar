from __future__ import annotations

from typing import Any


class SignalQualityReport:
    def __init__(self, config: dict[str, Any], db: Any):
        self.config = config
        self.db = db

    def render(self) -> str:
        lines = [
            "CryptoRadar Signal Quality Report",
            "",
            "Live and paper-tracked signals:",
            *self._live_signal_lines(),
            "",
            "Latest backtest:",
            *self._backtest_lines(),
            "",
            "ML readiness:",
            *self._ml_lines(),
            "",
            "This report is for proof and filtering only. CryptoRadar still does not trade.",
        ]
        return "\n".join(lines)

    def _live_signal_lines(self) -> list[str]:
        total = self.db.query_one("SELECT COUNT(*) AS count FROM signals")
        completed = self.db.query_one("SELECT COUNT(*) AS count FROM signals WHERE final_result IN ('win', 'loss')")
        lines = [
            f"- Total stored signals: {int(total['count']) if total else 0}",
            f"- Completed win/loss labels: {int(completed['count']) if completed else 0}",
        ]
        for signal_type in ("BUY", "SELL", "HIGH_RISK"):
            row = self.db.query_one(
                """
                SELECT
                    COUNT(*) AS count,
                    SUM(CASE WHEN final_result='win' THEN 1 ELSE 0 END) AS wins
                FROM signals
                WHERE signal_type=? AND final_result IN ('win', 'loss')
                """,
                (signal_type,),
            )
            count = int(row["count"]) if row else 0
            wins = int(row["wins"] or 0) if row else 0
            rate = "unknown" if count == 0 else f"{wins / count * 100:.1f}% ({wins}/{count})"
            label = "BUY win rate" if signal_type == "BUY" else f"{signal_type} accuracy"
            lines.append(f"- {label}: {rate}")
        return lines

    def _backtest_lines(self) -> list[str]:
        run = self.db.query_one("SELECT * FROM backtest_runs ORDER BY datetime(created_at) DESC LIMIT 1")
        if not run:
            return ["- No backtest run yet. Run python main.py --backtest after enough candles are stored."]
        payload = self.db.loads(run.get("payload_json"), {})
        strategies = payload.get("strategies", {}) if isinstance(payload, dict) else {}
        lines = [
            f"- Run ID: {run['id']}",
            f"- Status: {run['status']}",
            f"- Evaluated signals: {run['signal_count']}",
        ]
        crypto = strategies.get("cryptoradar", {})
        baseline_rates = [
            float(stats.get("success_rate"))
            for name, stats in strategies.items()
            if name != "cryptoradar" and stats.get("success_rate") is not None
        ]
        if crypto:
            crypto_rate = crypto.get("success_rate")
            lines.append(f"- CryptoRadar success rate: {crypto_rate}%")
            if baseline_rates and crypto_rate is not None:
                best_baseline = max(baseline_rates)
                verdict = "yes" if float(crypto_rate) >= best_baseline else "not yet"
                lines.append(f"- Beats best baseline: {verdict} (best baseline {best_baseline:.2f}%)")
            else:
                lines.append("- Beats best baseline: needs more baseline data")
        else:
            lines.append("- CryptoRadar success rate: no alert-level signals in latest backtest")
        return lines

    def _ml_lines(self) -> list[str]:
        examples = self.db.query_one("SELECT COUNT(*) AS count FROM ml_training_examples")
        count = int(examples["count"]) if examples else 0
        needed = int(self.config.get("ml", {}).get("min_training_samples", 30))
        if count < needed:
            return [f"- ML needs more labeled examples before trust: {count}/{needed}."]
        return [f"- ML has enough examples to train: {count}/{needed}. Check python main.py --ml-report."]
