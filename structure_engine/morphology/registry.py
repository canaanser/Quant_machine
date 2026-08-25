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
            # ===== 形态扩展（2026-08-26 小二陈）：9 → 18 种 =====
            "1_bullish_0_long_white": {
                "window": 1,
                "signal": "bullish",
                "generation": 0,
                "atomics": [
                    {"class": "DirectionalBody", "params": {"direction": "bullish", "min_ratio": 0.65}},
                ],
                "threshold": {"min": 0.65},
                "combine": "all",
                "human_readable": "长阳线"
            },
            "1_bearish_0_long_dark": {
                "window": 1,
                "signal": "bearish",
                "generation": 0,
                "atomics": [
                    {"class": "DirectionalBody", "params": {"direction": "bearish", "min_ratio": 0.65}},
                ],
                "threshold": {"min": 0.65},
                "combine": "all",
                "human_readable": "长阴线"
            },
            "1_bullish_0_hammer": {
                "window": 1,
                "signal": "bullish",
                "generation": 0,
                "atomics": [
                    {"class": "HammerDetector", "params": {"min_ratio": 2.0, "max_body_ratio": 0.5}},
                ],
                "threshold": {"min": 2.0},
                "combine": "all",
                "human_readable": "锤子线"
            },
            "2_bearish_0_dark_cloud": {
                "window": 2,
                "signal": "bearish",
                "generation": 0,
                "atomics": [
                    {"class": "PiercingDetector", "params": {"pattern_type": "dark_cloud", "depth": 0.5}},
                ],
                "threshold": {"min": 0.5},
                "combine": "all",
                "human_readable": "乌云盖顶"
            },
            "2_bullish_0_piercing": {
                "window": 2,
                "signal": "bullish",
                "generation": 0,
                "atomics": [
                    {"class": "PiercingDetector", "params": {"pattern_type": "piercing", "depth": 0.5}},
                ],
                "threshold": {"min": 0.5},
                "combine": "all",
                "human_readable": "刺透线"
            },
            "3_bearish_0_evening_star": {
                "window": 3,
                "signal": "bearish",
                "generation": 0,
                "atomics": [
                    {"class": "StarDetector", "params": {"star_type": "evening", "body_threshold": 0.5, "small_threshold": 0.3}},
                ],
                "threshold": {"min": 0.5},
                "combine": "all",
                "human_readable": "黄昏之星"
            },
            "3_bullish_0_morning_star": {
                "window": 3,
                "signal": "bullish",
                "generation": 0,
                "atomics": [
                    {"class": "StarDetector", "params": {"star_type": "morning", "body_threshold": 0.5, "small_threshold": 0.3}},
                ],
                "threshold": {"min": 0.5},
                "combine": "all",
                "human_readable": "早晨之星"
            },
            "5_bullish_0_rising_three": {
                "window": 5,
                "signal": "bullish",
                "generation": 0,
                "atomics": [
                    {"class": "ThreeMethodsDetector", "params": {"pattern_type": "rising", "body_threshold": 0.5, "small_threshold": 0.4}},
                ],
                "threshold": {"min": 0.5},
                "combine": "all",
                "human_readable": "上升三法"
            },
            "5_bearish_0_falling_three": {
                "window": 5,
                "signal": "bearish",
                "generation": 0,
                "atomics": [
                    {"class": "ThreeMethodsDetector", "params": {"pattern_type": "falling", "body_threshold": 0.5, "small_threshold": 0.4}},
                ],
                "threshold": {"min": 0.5},
                "combine": "all",
                "human_readable": "下降三法"
            },
            # ===== 形态扩展第二批（2026-08-26 小二陈）：18 → 21 种 =====
            "1_bearish_0_shooting_star": {
                "window": 1,
                "signal": "bearish",
                "generation": 0,
                "atomics": [
                    {"class": "ShadowBodyDetector", "params": {"shadow_type": "upper", "min_shadow_ratio": 2.0, "max_body_ratio": 0.5, "direction": "bearish"}},
                ],
                "threshold": {"min": 2.0},
                "combine": "all",
                "human_readable": "射击之星"
            },
            "1_bullish_0_inverted_hammer": {
                "window": 1,
                "signal": "bullish",
                "generation": 0,
                "atomics": [
                    {"class": "ShadowBodyDetector", "params": {"shadow_type": "upper", "min_shadow_ratio": 2.0, "max_body_ratio": 0.5, "direction": "bullish"}},
                ],
                "threshold": {"min": 2.0},
                "combine": "all",
                "human_readable": "倒锤子线"
            },
            "1_bearish_0_hanging_man": {
                "window": 1,
                "signal": "bearish",
                "generation": 0,
                "atomics": [
                    {"class": "ShadowBodyDetector", "params": {"shadow_type": "lower", "min_shadow_ratio": 2.0, "max_body_ratio": 0.5, "direction": "bearish"}},
                ],
                "threshold": {"min": 2.0},
                "combine": "all",
                "human_readable": "上吊线"
            },
        })

    def get(self, pattern_id: str) -> dict:
        return self._registry.get(pattern_id, None)

    def list_all(self) -> List[dict]:
        return [{"id": k, **v} for k, v in self._registry.items()]


REGISTRY = MorphologyRegistry()