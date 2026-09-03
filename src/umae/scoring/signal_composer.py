"""Signal composer that produces final signal from CompositeSignal."""

from __future__ import annotations

import logging

from umae.domain.enums import MarketRegime, SignalType, Timeframe
from umae.domain.models import CompositeSignal, SignalScore, TimeframeSignal

logger = logging.getLogger(__name__)

_MIN_SCORE_THRESHOLD = 0.15
_MAX_SCORE = 1.0

_HTF_TIMEFRAMES = {Timeframe.H4, Timeframe.H6, Timeframe.H12, Timeframe.D1, Timeframe.W1}
_MTF_TIMEFRAMES = {Timeframe.M15, Timeframe.M20, Timeframe.M30, Timeframe.H1, Timeframe.H2}
_LTF_TIMEFRAMES = {Timeframe.M1, Timeframe.M3, Timeframe.M5}

_REGIME_BIAS: dict[MarketRegime, float] = {
    MarketRegime.TRENDING_UP: 0.1,
    MarketRegime.TRENDING_DOWN: -0.1,
    MarketRegime.RANGING: 0.0,
    MarketRegime.HIGH_VOLATILITY: 0.0,
    MarketRegime.LOW_VOLATILITY: 0.0,
    MarketRegime.BREAKOUT: 0.0,
    MarketRegime.UNCERTAIN: 0.0,
}

_REGIME_PENALTY: dict[MarketRegime, float] = {
    MarketRegime.TRENDING_UP: 1.0,
    MarketRegime.TRENDING_DOWN: 1.0,
    MarketRegime.RANGING: 0.85,
    MarketRegime.HIGH_VOLATILITY: 0.75,
    MarketRegime.LOW_VOLATILITY: 0.9,
    MarketRegime.BREAKOUT: 0.7,
    MarketRegime.UNCERTAIN: 0.8,
}


class SignalComposer:
    """Takes a CompositeSignal and produces a final signal with confidence.

    Applies minimum confluence rules, regime adjustments, and generates
    reason codes explaining the decision.
    """

    def __init__(
        self,
        min_score_threshold: float = _MIN_SCORE_THRESHOLD,
        htf_weight: float = 3.0,
        mtf_weight: float = 2.0,
        ltf_weight: float = 1.0,
        regime_adjustment: bool = True,
        regime_bias: dict[MarketRegime, float] | None = None,
        regime_penalty: dict[MarketRegime, float] | None = None,
    ) -> None:
        self._min_score_threshold = min_score_threshold
        self._htf_weight = htf_weight
        self._mtf_weight = mtf_weight
        self._ltf_weight = ltf_weight
        self._regime_adjustment = regime_adjustment
        self._regime_bias = regime_bias or _REGIME_BIAS
        self._regime_penalty = regime_penalty or _REGIME_PENALTY

    def compose(self, composite: CompositeSignal) -> CompositeSignal:
        """Produce final signal from a composite.

        Args:
            composite: Input CompositeSignal with timeframe signals.

        Returns:
            New CompositeSignal with final signal, score, and reason codes.
        """
        signals = composite.timeframe_signals

        if not signals:
            return self._no_signal(composite, ["no_timeframe_data"])

        if composite.score.raw_score == 0.0 and composite.signal == SignalType.NO_SIGNAL:
            return composite

        contributing = dict(composite.contributing_factors)

        htf_sigs = {tf: s for tf, s in signals.items() if tf in _HTF_TIMEFRAMES}
        mtf_sigs = {tf: s for tf, s in signals.items() if tf in _MTF_TIMEFRAMES}
        ltf_sigs = {tf: s for tf, s in signals.items() if tf in _LTF_TIMEFRAMES}

        htf_score = self._weighted_group_score(htf_sigs, self._htf_weight)
        mtf_score = self._weighted_group_score(mtf_sigs, self._mtf_weight)
        ltf_score = self._weighted_group_score(ltf_sigs, self._ltf_weight)

        contributing["htf_score"] = round(htf_score, 4)
        contributing["mtf_score"] = round(mtf_score, 4)
        contributing["ltf_score"] = round(ltf_score, 4)

        total_weight = self._htf_weight + self._mtf_weight + self._ltf_weight
        raw_score = (htf_score + mtf_score + ltf_score) / total_weight

        # Score breakdown for auditability
        score_breakdown: dict[str, float] = {
            "htf_bias": round(htf_score, 4),
            "trend_alignment": 0.0,
            "momentum": 0.0,
            "volume": 0.0,
            "structure": 0.0,
            "regime_adjustment": 0.0,
        }

        reasons: list[str] = []

        if composite.regime != MarketRegime.UNCERTAIN:
            reasons.append(f"regime:{composite.regime.value}")

        regime_bias_before = raw_score
        if composite.regime in _REGIME_BIAS:
            raw_score += _REGIME_BIAS[composite.regime]
        score_breakdown["regime_adjustment"] = round(raw_score - regime_bias_before, 4)

        regime_penalty_before = raw_score
        if self._regime_adjustment and composite.regime in _REGIME_PENALTY:
            penalty = _REGIME_PENALTY[composite.regime]
            raw_score *= penalty
            if penalty < 1.0:
                reasons.append(f"regime_penalty:{composite.regime.value}:{penalty:.2f}")
        score_breakdown["regime_adjustment"] = round(
            raw_score - regime_penalty_before + score_breakdown["regime_adjustment"], 4
        )

        raw_score = max(-_MAX_SCORE, min(_MAX_SCORE, raw_score))

        # HTF unanimous logic — only count non-NEUTRAL HTF signals
        if htf_sigs:
            htf_directions = [s.signal for s in htf_sigs.values() if s.signal != SignalType.NEUTRAL]
            if htf_directions:
                if all(d == SignalType.UP for d in htf_directions):
                    reasons.append("htf_unanimous_bullish")
                elif all(d == SignalType.DOWN for d in htf_directions):
                    reasons.append("htf_unanimous_bearish")
                else:
                    reasons.append("htf_mixed")

        tf_directions = []
        for tf in sorted(signals, key=lambda x: x.minutes, reverse=True):
            sig = signals[tf]
            if sig.signal in (SignalType.UP, SignalType.DOWN):
                tf_directions.append((tf, sig.signal))

        bullish_count = sum(1 for _, d in tf_directions if d == SignalType.UP)
        bearish_count = sum(1 for _, d in tf_directions if d == SignalType.DOWN)
        total_signal_count = len(tf_directions)

        reasons.append(
            f"confluence:{bullish_count}up:{bearish_count}down:{total_signal_count}total"
        )

        if total_signal_count < 2:
            reasons.append("low_confluence_warning")

        signal_type = SignalType.NEUTRAL
        if raw_score > self._min_score_threshold:
            signal_type = SignalType.UP
        elif raw_score < -self._min_score_threshold:
            signal_type = SignalType.DOWN

        top_reasons: list[str] = []
        for tf in sorted(signals, key=lambda x: x.minutes, reverse=True):
            top_reasons.extend(f"{tf.value}:{r}" for r in signals[tf].reason_codes[:1])

        all_reasons = reasons + top_reasons

        # Build contributors from reason codes — each must map to actual computed feature
        contributors: list[str] = []
        if "htf_unanimous_bullish" in reasons:
            contributors.append("+ HTF bullish bias")
        elif "htf_unanimous_bearish" in reasons:
            contributors.append("- HTF bearish bias")
        elif "htf_mixed" in reasons:
            contributors.append("~ Mixed HTF evidence")

        for tf in sorted(signals, key=lambda x: x.minutes, reverse=True):
            for r in signals[tf].reason_codes[:2]:
                if "ema_bullish" in r:
                    contributors.append(f"+ {tf.value}: EMA alignment")
                elif "ema_bearish" in r:
                    contributors.append(f"- {tf.value}: EMA alignment")
                elif "price_above" in r:
                    contributors.append(f"+ {tf.value}: Price above trend EMA")
                elif "price_below" in r:
                    contributors.append(f"- {tf.value}: Price below trend EMA")
                elif "rsi_oversold" in r:
                    contributors.append(f"+ {tf.value}: RSI oversold")
                elif "rsi_overbought" in r:
                    contributors.append(f"- {tf.value}: RSI overbought")
                elif "bullish_structure" in r:
                    contributors.append(f"+ {tf.value}: Bullish structure")
                elif "bearish_structure" in r:
                    contributors.append(f"- {tf.value}: Bearish structure")
                elif "macd_bullish" in r:
                    contributors.append(f"+ {tf.value}: MACD bullish")
                elif "macd_bearish" in r:
                    contributors.append(f"- {tf.value}: MACD bearish")
                elif "volume_spike" in r:
                    contributors.append(f"+ {tf.value}: Volume spike")

        # NO_SIGNAL conditions: insufficient data, conflicting, uncertain regime
        no_signal_reasons = []
        if total_signal_count < 2:
            no_signal_reasons.append("insufficient_confluence")
        if "htf_mixed" in reasons:
            no_signal_reasons.append("mixed_htf_evidence")

        return CompositeSignal(
            timestamp=composite.timestamp,
            symbol=composite.symbol,
            asset_type=composite.asset_type,
            exchange=composite.exchange,
            price=composite.price,
            signal=signal_type,
            score=SignalScore(raw_score=round(raw_score, 4)),
            timeframe_signals=signals,
            regime=composite.regime,
            reason_codes=all_reasons[:12],
            contributing_factors={
                **contributing,
                "score_breakdown": score_breakdown,
                "contributors": contributors,
            },
            model_version=composite.model_version,
            data_version=composite.data_version,
        )

    def _weighted_group_score(
        self,
        signals: dict[Timeframe, TimeframeSignal],
        base_weight: float,
    ) -> float:
        if not signals:
            return 0.0

        total = 0.0
        count = 0
        for sig in signals.values():
            total += sig.score.raw_score * base_weight
            count += 1

        return total / count if count > 0 else 0.0

    def _no_signal(self, composite: CompositeSignal, reasons: list[str]) -> CompositeSignal:
        return CompositeSignal(
            timestamp=composite.timestamp,
            symbol=composite.symbol,
            asset_type=composite.asset_type,
            exchange=composite.exchange,
            price=composite.price,
            signal=SignalType.NO_SIGNAL,
            score=SignalScore(raw_score=0.0),
            timeframe_signals={},
            regime=composite.regime,
            reason_codes=reasons,
            contributing_factors={},
            model_version=composite.model_version,
            data_version=composite.data_version,
        )
