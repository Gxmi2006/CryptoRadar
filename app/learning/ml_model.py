from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FEATURE_NAMES = [
    "score",
    "buy_score",
    "sell_score",
    "hold_score",
    "high_risk_score",
    "rsi",
    "macd_histogram",
    "relative_volume",
    "volume_usdt",
    "change_1h",
    "change_4h",
    "change_24h",
    "atr_pct",
    "distance_to_support_pct",
    "distance_to_resistance_pct",
    "btc_bearish",
    "eth_bearish",
    "signal_buy",
    "signal_sell",
    "signal_high_risk",
    "knowledge_score",
    "knowledge_source_count",
    "data_quality_score",
]


QUALITY_SCORES = {
    "good": 1.0,
    "thin": 0.65,
    "low_volume": 0.35,
    "missing_candles": 0.2,
    "unknown": 0.5,
}


class FutureMLModel:
    """Local ML prediction helper.

    This intentionally trains a small local model on CryptoRadar's saved signal
    outcomes. It is not LLM fine-tuning and it does not trade.
    """

    def __init__(self, db: Any, config: dict[str, Any] | None = None, project_root: Path | None = None):
        self.db = db
        self.config = config or {}
        self.project_root = project_root or Path.cwd()
        self._artifact: dict[str, Any] | None = None

    def build_training_examples(self) -> dict[str, Any]:
        rows = self.db.query(
            """
            SELECT id, symbol, signal_type, score, payload_json, final_result
            FROM signals
            WHERE final_result IN ('win', 'loss')
            """
        )
        inserted = 0
        for row in rows:
            signal = self._signal_from_row(row)
            quality = self._quality_for_symbol(row["symbol"])
            features = extract_ml_features(signal, quality)
            label = 1 if row["final_result"] == "win" else 0
            self.db.execute(
                """
                INSERT INTO ml_training_examples(signal_id, symbol, signal_type, label, features_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(signal_id) DO UPDATE SET
                    label=excluded.label,
                    features_json=excluded.features_json
                """,
                (row["id"], row["symbol"], row["signal_type"], label, self.db.dumps(features)),
            )
            inserted += 1
        return {"examples": inserted}

    def train(self) -> str:
        if not self.config.get("ml", {}).get("enabled", True):
            return "ML training is disabled in config."
        self.build_training_examples()
        examples = self.db.query("SELECT label, features_json FROM ml_training_examples ORDER BY id")
        min_samples = int(self.config.get("ml", {}).get("min_training_samples", 30))
        if len(examples) < min_samples:
            report = f"Need at least {min_samples} labeled win/loss examples before training. Current examples: {len(examples)}."
            self._record_training_run("not_trained", "none", len(examples), 0, 0, None, report, {})
            return report
        labels = [int(row["label"]) for row in examples]
        if len(set(labels)) < 2:
            report = "ML training needs both win and loss examples before fitting a model."
            self._record_training_run("not_trained", "none", len(examples), 0, 0, None, report, {})
            return report
        if min(labels.count(0), labels.count(1)) < 2:
            report = "ML training needs at least two wins and two losses before fitting a reliable holdout split."
            self._record_training_run("not_trained", "none", len(examples), 0, 0, None, report, {})
            return report
        try:
            from joblib import dump
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.linear_model import LogisticRegression
            from sklearn.metrics import accuracy_score
            from sklearn.model_selection import train_test_split
            from sklearn.pipeline import make_pipeline
            from sklearn.preprocessing import StandardScaler
        except Exception as exc:
            report = f"ML dependencies are not installed. Run: pip install -r requirements.txt. Missing: {type(exc).__name__}."
            self._record_training_run("not_trained", "missing_dependency", len(examples), 0, 0, None, report, {})
            return report

        x = [self._feature_vector(self.db.loads(row["features_json"], {})) for row in examples]
        random_forest_min = int(self.config.get("ml", {}).get("random_forest_min_samples", 200))
        if len(examples) >= random_forest_min:
            model_type = "random_forest"
            model = RandomForestClassifier(n_estimators=120, max_depth=8, random_state=42, class_weight="balanced")
        else:
            model_type = "logistic_regression"
            model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))

        test_size = float(self.config.get("ml", {}).get("test_size", 0.25))
        x_train, x_test, y_train, y_test = train_test_split(x, labels, test_size=test_size, random_state=42, stratify=labels)
        model.fit(x_train, y_train)
        accuracy = float(accuracy_score(y_test, model.predict(x_test))) if x_test else None
        version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        artifact = {
            "model": model,
            "feature_names": FEATURE_NAMES,
            "model_version": version,
            "model_type": model_type,
        }
        path = self.model_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        dump(artifact, path)
        report = (
            f"Trained {model_type} model version {version} with {len(examples)} examples. "
            f"Holdout accuracy: {accuracy:.1%}."
        )
        self._record_training_run(version, model_type, len(examples), len(x_train), len(x_test), accuracy, report, {"path": str(path)})
        self._artifact = artifact
        return report

    def predict_for_signal(self, signal: dict[str, Any]) -> dict[str, Any] | None:
        if not self.config.get("ml", {}).get("enabled", True):
            return None
        artifact = self._load_artifact()
        if not artifact:
            return None
        quality = self._quality_for_symbol(signal.get("symbol", ""))
        features = extract_ml_features(signal, quality)
        vector = [float(features.get(name, 0)) for name in artifact.get("feature_names", FEATURE_NAMES)]
        model = artifact["model"]
        probability = 0.5
        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba([vector])[0]
            classes_attr = getattr(model, "classes_", None)
            if classes_attr is None and hasattr(model, "__getitem__"):
                classes_attr = getattr(model[-1], "classes_", [0, 1])
            if classes_attr is None:
                classes_attr = [0, 1]
            classes = list(classes_attr)
            probability = float(probabilities[classes.index(1)]) if 1 in classes else float(max(probabilities))
        else:
            probability = float(model.predict([vector])[0])
        data_quality = features.get("data_quality", "unknown")
        quality_score = float(features.get("data_quality_score", 0.5))
        risk_score = _clamp((1 - probability) * 0.75 + (1 - quality_score) * 0.25)
        confidence_score = _clamp(abs(probability - 0.5) * 2 + quality_score * 0.1)
        return {
            "success_probability": round(_clamp(probability), 4),
            "risk_score": round(risk_score, 4),
            "confidence_score": round(confidence_score, 4),
            "data_quality": data_quality,
            "model_version": artifact.get("model_version", "unknown"),
            "model_type": artifact.get("model_type", "unknown"),
        }

    def predict(self, features: dict[str, Any]) -> dict[str, float]:
        signal = {"features": features, "indicators": features, "score": features.get("score", 0)}
        prediction = self.predict_for_signal(signal)
        if not prediction:
            return {"success_probability": 0.5, "risk_score": 0.5, "confidence_score": 0.5}
        return {
            "success_probability": float(prediction["success_probability"]),
            "risk_score": float(prediction["risk_score"]),
            "confidence_score": float(prediction["confidence_score"]),
        }

    def report(self) -> str:
        examples = self.db.query_one("SELECT COUNT(*) AS count FROM ml_training_examples")
        predictions = self.db.query_one("SELECT COUNT(*) AS count FROM ml_predictions")
        last_run = self.db.query_one("SELECT * FROM ml_training_runs ORDER BY id DESC LIMIT 1")
        lines = [
            "CryptoRadar ML Report",
            f"Training examples: {int(examples['count']) if examples else 0}",
            f"Predictions stored: {int(predictions['count']) if predictions else 0}",
            f"Model artifact: {self.model_path()}",
        ]
        if last_run:
            lines.extend(
                [
                    f"Last model version: {last_run.get('model_version')}",
                    f"Last model type: {last_run.get('model_type')}",
                    f"Last sample count: {last_run.get('sample_count')}",
                    f"Last accuracy: {last_run.get('accuracy')}",
                    f"Last report: {last_run.get('report_text')}",
                ]
            )
        else:
            lines.append("Last training run: none")
        return "\n".join(lines)

    def model_path(self) -> Path:
        path = Path(self.config.get("ml", {}).get("model_path", "./data/ml/model.joblib"))
        return path if path.is_absolute() else self.project_root / path

    def _load_artifact(self) -> dict[str, Any] | None:
        if self._artifact is not None:
            return self._artifact
        path = self.model_path()
        if not path.exists():
            return None
        try:
            from joblib import load

            artifact = load(path)
        except Exception:
            return None
        self._artifact = artifact
        return artifact

    def _feature_vector(self, features: dict[str, Any]) -> list[float]:
        return [float(features.get(name, 0)) for name in FEATURE_NAMES]

    def _signal_from_row(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = self.db.loads(row.get("payload_json"), {})
        if isinstance(payload, dict):
            payload.setdefault("id", row.get("id"))
            payload.setdefault("symbol", row.get("symbol"))
            payload.setdefault("signal_type", row.get("signal_type"))
            payload.setdefault("score", row.get("score"))
            return payload
        return dict(row)

    def _quality_for_symbol(self, symbol: str) -> dict[str, Any] | None:
        if not symbol:
            return None
        return self.db.query_one("SELECT * FROM symbol_data_quality WHERE symbol=?", (symbol,))

    def _record_training_run(
        self,
        version: str,
        model_type: str,
        sample_count: int,
        train_count: int,
        test_count: int,
        accuracy: float | None,
        report: str,
        payload: dict[str, Any],
    ) -> None:
        self.db.execute(
            """
            INSERT INTO ml_training_runs(
                model_version, model_type, sample_count, train_count, test_count,
                accuracy, report_text, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (version, model_type, sample_count, train_count, test_count, accuracy, report, self.db.dumps(payload)),
        )


def extract_ml_features(signal: dict[str, Any], quality: dict[str, Any] | None = None) -> dict[str, Any]:
    indicators = signal.get("indicators") or {}
    features = signal.get("features") or {}
    scores = signal.get("score_details") or {}
    signal_type = str(signal.get("signal_type") or signal.get("type") or "").upper()
    data_quality = (quality or {}).get("data_quality", signal.get("data_quality", "unknown"))
    row: dict[str, Any] = {
        "score": _float(signal.get("score")),
        "buy_score": _float(scores.get("buy_score")),
        "sell_score": _float(scores.get("sell_score")),
        "hold_score": _float(scores.get("hold_score")),
        "high_risk_score": _float(scores.get("high_risk_score")),
        "rsi": _float(indicators.get("rsi", features.get("rsi", 50))),
        "macd_histogram": _float(indicators.get("macd_histogram", features.get("macd_histogram"))),
        "relative_volume": _float(indicators.get("relative_volume", features.get("relative_volume", 1))),
        "volume_usdt": _float(features.get("volume_usdt", signal.get("volume_usdt"))),
        "change_1h": _float(features.get("change_1h")),
        "change_4h": _float(features.get("change_4h")),
        "change_24h": _float(features.get("change_24h")),
        "atr_pct": _float(indicators.get("atr_pct", features.get("atr_pct"))),
        "distance_to_support_pct": _float(features.get("distance_to_support_pct")),
        "distance_to_resistance_pct": _float(features.get("distance_to_resistance_pct")),
        "btc_bearish": 1.0 if signal.get("btc_trend") == "bearish" or features.get("btc_trend") == "bearish" else 0.0,
        "eth_bearish": 1.0 if signal.get("eth_trend") == "bearish" or features.get("eth_trend") == "bearish" else 0.0,
        "signal_buy": 1.0 if signal_type == "BUY" else 0.0,
        "signal_sell": 1.0 if signal_type == "SELL" else 0.0,
        "signal_high_risk": 1.0 if signal_type == "HIGH_RISK" else 0.0,
        "knowledge_score": _float(features.get("knowledge_score")),
        "knowledge_source_count": float(len(signal.get("knowledge_sources_used") or [])),
        "data_quality_score": QUALITY_SCORES.get(str(data_quality), QUALITY_SCORES["unknown"]),
        "data_quality": str(data_quality),
    }
    return row


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
