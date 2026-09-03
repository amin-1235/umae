"""Confidence calibrator for signal scores."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from umae.domain.models import CompositeSignal, SignalScore

if TYPE_CHECKING:
    from umae.domain.enums import AssetType, MarketRegime

logger = logging.getLogger(__name__)

_MIN_SAMPLES_FOR_CALIBRATION = 30


class _IsotonicModel:
    """Minimal isotonic regression model using Pool Adjacent Violators."""

    def __init__(self, x_thresholds: np.ndarray, y_values: np.ndarray) -> None:
        self._x = x_thresholds
        self._y = y_values

    def predict(self, x: np.ndarray) -> np.ndarray:
        result = np.interp(x, self._x, self._y)
        return np.asarray(np.clip(result, 0.0, 1.0))


def _pav_algorithm(x: np.ndarray, y: np.ndarray) -> _IsotonicModel:
    """Pool Adjacent Violators for isotonic regression."""
    order = np.argsort(x)
    x_sorted = x[order]
    y_sorted = y[order].copy()

    blocks = [[float(y_sorted[0])]]
    for i in range(1, len(y_sorted)):
        blocks.append([float(y_sorted[i])])

    changed = True
    while changed:
        changed = False
        new_blocks: list[list[float]] = []
        i = 0
        while i < len(blocks):
            current = blocks[i][:]
            while i + 1 < len(blocks) and np.mean(current) > np.mean(blocks[i + 1]):
                current.extend(blocks[i + 1])
                i += 1
                changed = True
            new_blocks.append(current)
            i += 1
        blocks = new_blocks

    thresholds = []
    values = []
    idx = 0
    for block in blocks:
        mean_val = float(np.mean(block))
        end_idx = idx + len(block) - 1
        thresholds.append(float(x_sorted[end_idx]))
        values.append(mean_val)
        idx += len(block)

    thresholds = [float(x_sorted[0]), *thresholds]
    values = [float(np.mean(blocks[0])), *values]

    return _IsotonicModel(np.array(thresholds), np.array(values))


class ConfidenceCalibrator:
    """Calibrates raw scores to confidence values.

    Supports isotonic regression and Platt scaling.
    Per-asset and per-regime calibration.
    """

    def __init__(
        self,
        method: str = "isotonic",
        store_dir: str | Path | None = None,
        min_samples: int = _MIN_SAMPLES_FOR_CALIBRATION,
    ) -> None:
        self._method = method
        self._store_dir = Path(store_dir) if store_dir else None
        self._min_samples = min_samples
        self._models: dict[str, Any] = {}
        self._load_models()

    def _load_models(self) -> None:
        if self._store_dir is None or not self._store_dir.exists():
            return

        for path in self._store_dir.glob("calibrator_*.json"):
            try:
                data = json.loads(path.read_text())
                key = data["key"]
                if data["method"] == "isotonic":
                    self._models[key] = _IsotonicModel(
                        np.array(data["x_thresholds"]),
                        np.array(data["y_values"]),
                    )
            except Exception:
                logger.warning("Failed to load calibration model: %s", path)

    def _model_key(
        self,
        asset_type: AssetType | None,
        regime: MarketRegime | None,
    ) -> str:
        parts = ["global"]
        if asset_type is not None:
            parts = [asset_type.value]
        if regime is not None:
            parts.append(regime.value)
        return ":".join(parts)

    def fit(
        self,
        scores: list[float],
        outcomes: list[int],
        asset_type: AssetType | None = None,
        regime: MarketRegime | None = None,
    ) -> bool:
        """Fit calibration model from historical scores and outcomes.

        Args:
            scores: Raw signal scores.
            outcomes: Binary outcomes (1=correct, 0=incorrect).
            asset_type: Optional asset type for per-asset calibration.
            regime: Optional regime for per-regime calibration.

        Returns:
            True if model was fitted, False if insufficient data.
        """
        if len(scores) < self._min_samples:
            logger.debug("Insufficient samples for calibration: %d", len(scores))
            return False

        x = np.array(scores, dtype=np.float64)
        y = np.array(outcomes, dtype=np.float64)

        key = self._model_key(asset_type, regime)

        if self._method == "isotonic":
            self._models[key] = _pav_algorithm(x, y)
        elif self._method == "platt":
            self._models[key] = self._fit_platt(x, y)
        else:
            logger.error("Unknown calibration method: %s", self._method)
            return False

        self._save_model(key)
        logger.info("Fitted calibration model for %s with %d samples", key, len(scores))
        return True

    def _fit_platt(self, x: np.ndarray, y: np.ndarray) -> dict[str, Any]:
        a = float(x.mean())
        b = 1.0
        for _ in range(20):
            p = 1.0 / (1.0 + np.exp(-(a * x + b)))
            grad_a = float(np.sum((p - y) * x))
            grad_b = float(np.sum(p - y))
            a -= 0.01 * grad_a
            b -= 0.01 * grad_b
        return {"method": "platt", "a": a, "b": b}

    def calibrate(
        self,
        composite: CompositeSignal,
        asset_type: AssetType | None = None,
        regime: MarketRegime | None = None,
    ) -> CompositeSignal:
        """Calibrate the score of a CompositeSignal.

        Args:
            composite: Signal to calibrate.
            asset_type: Asset type override for calibration lookup.
            regime: Regime override for calibration lookup.

        Returns:
            New CompositeSignal with calibrated confidence.
        """
        raw = composite.score.raw_score
        at = asset_type or composite.asset_type
        rg = regime or composite.regime

        confidence = self._calibrate_score(raw, at, rg)

        new_score = SignalScore(
            raw_score=raw,
            calibrated_confidence=confidence,
            calibration_method=self._method,
            calibration_version="1.0.0",
        )

        return CompositeSignal(
            timestamp=composite.timestamp,
            symbol=composite.symbol,
            asset_type=composite.asset_type,
            exchange=composite.exchange,
            price=composite.price,
            signal=composite.signal,
            score=new_score,
            timeframe_signals=composite.timeframe_signals,
            regime=composite.regime,
            reason_codes=composite.reason_codes,
            contributing_factors=composite.contributing_factors,
            model_version=composite.model_version,
            data_version=composite.data_version,
        )

    def _calibrate_score(
        self,
        raw_score: float,
        asset_type: AssetType,
        regime: MarketRegime,
    ) -> float:
        specific_key = self._model_key(asset_type, regime)
        model = self._models.get(specific_key)

        if model is None:
            generic_key = self._model_key(asset_type, None)
            model = self._models.get(generic_key)

        if model is None:
            global_key = self._model_key(None, None)
            model = self._models.get(global_key)

        if model is None:
            return self._fallback_confidence(raw_score)

        x = np.array([raw_score])
        try:
            result = model.predict(x)
            return float(np.clip(result[0], 0.0, 1.0))
        except Exception:
            return self._fallback_confidence(raw_score)

    def _fallback_confidence(self, raw_score: float) -> float:
        return min(1.0, abs(raw_score) * 2.0)

    def _save_model(self, key: str) -> None:
        if self._store_dir is None:
            return

        self._store_dir.mkdir(parents=True, exist_ok=True)
        model = self._models[key]
        filename = self._store_dir / f"calibrator_{key.replace(':', '_')}.json"

        if self._method == "isotonic" and isinstance(model, _IsotonicModel):
            data = {
                "key": key,
                "method": "isotonic",
                "x_thresholds": model._x.tolist(),
                "y_values": model._y.tolist(),
            }
            filename.write_text(json.dumps(data, indent=2))
        elif self._method == "platt" and isinstance(model, dict):
            data = {"key": key, **model}
            filename.write_text(json.dumps(data, indent=2))

    def get_stats(self) -> dict[str, Any]:
        """Return calibration statistics."""
        return {
            "method": self._method,
            "model_count": len(self._models),
            "keys": list(self._models.keys()),
            "store_dir": str(self._store_dir) if self._store_dir else None,
        }
