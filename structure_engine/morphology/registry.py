from typing import Dict, List, Any
from structure_engine.morphology.atomic import (
    BodyRatio,
    ShadowRatio,
    GapDetector,
    EngulfingDetector,
    InsideDetector,
    ConsecutiveBars,
    VolumeSpike,
)


class MorphologyRegistry:
    def __init__(self):
        self._registry: Dict[str, dict] = {}
        self._build_registry()

    def _build_registry(self):
        self._registry.update({
            "1_bullish_0_body": {
                "window": 1,
                "signal": "bullish",
                "generation": 0,
                "atomics": [
                    {"class": "BodyRatio", "params": {"min_ratio": 0.25, "max_ratio": 0.65}},
                ],
                "threshold": {"min": 0.25, "max": 0.65},
                "combine": "all",
                "human_readable": "实体适中"
            },
            "1_bullish_0_shadow_lower": {
                "window": 1,
                "signal": "bullish",
                "generation": 0,
                "atomics": [
                    {"class": "ShadowRatio", "params": {"shadow_type": "lower", "min_ratio": 2.5}},
                ],
                "threshold": {"min": 2.5},
                "combine": "all",
                "human_readable": "长下影线"
            },
            "1_bearish_0_shadow_upper": {
                "window": 1,
                "signal": "bearish",
                "generation": 0,
                "atomics": [
                    {"class": "ShadowRatio", "params": {"shadow_type": "upper", "min_ratio": 2.5}},
                ],
                "threshold": {"min": 2.5},
                "combine": "all",
                "human_readable": "长上影线"
            },
            "1_neutral_0_doji": {
                "window": 1,
                "signal": "neutral",
                "generation": 0,
                "atomics": [
                    {"class": "BodyRatio", "params": {"min_ratio": 0.0, "max_ratio": 0.08}},
                ],
                "threshold": {"min": 0.0, "max": 0.08},
                "combine": "all",
                "human_readable": "十字星"
            },
            "2_bullish_0_engulfing": {
                "window": 2,
                "signal": "bullish",
                "generation": 0,
                "atomics": [
                    {"class": "EngulfingDetector", "params": {"engulfing_type": "bullish"}},
                ],
                "threshold": {"min": 0.5},
                "combine": "all",
                "human_readable": "看涨吞没"
            },
            "2_bearish_0_engulfing": {
                "window": 2,
                "signal": "bearish",
                "generation": 0,
                "atomics": [
                    {"class": "EngulfingDetector", "params": {"engulfing_type": "bearish"}},
                ],
                "threshold": {"min": 0.5},
                "combine": "all",
                "human_readable": "看跌吞没"
            },
            "2_neutral_0_inside": {
                "window": 2,
                "signal": "neutral",
                "generation": 0,
                "atomics": [
                    {"class": "InsideDetector", "params": {}},
                ],
                "threshold": {"min": 0.5},
                "combine": "all",
                "human_readable": "内包线"
            },
            "3_bullish_0_three_white_soldiers": {
                "window": 3,
                "signal": "bullish",
                "generation": 0,
                "atomics": [
                    {"class": "ConsecutiveBars", "params": {"direction": "up", "count": 3}},
                ],
                "threshold": {"min": 1.0},
                "combine": "all",
                "human_readable": "三白兵"
            },
            "3_bearish_0_three_black_crows": {
                "window": 3,
                "signal": "bearish",
                "generation": 0,
                "atomics": [
                    {"class": "ConsecutiveBars", "params": {"direction": "down", "count": 3}},
                ],
                "threshold": {"min": 1.0},
                "combine": "all",
                "human_readable": "三乌鸦"
            },
        })

    def get(self, pattern_id: str) -> dict:
        return self._registry.get(pattern_id, None)

    def list_all(self) -> List[dict]:
        return [{"id": k, **v} for k, v in self._registry.items()]


REGISTRY = MorphologyRegistry()