"""
Topic Detection Configuration

Centralizes all domain-specific term lists used for detecting topic types.
This allows easy extension without modifying the core service logic.
"""

from typing import TypedDict


class TopicTerms(TypedDict):
    """Term lists for detecting a specific topic type."""
    detect: list[str]
    graph_confirm: list[str] | None


TOPIC_TERMS: dict[str, TopicTerms] = {
    "semiconductor": {
        "detect": [
            "mos", "mosfet", "finfet",
            "晶体管", "场效应管", "栅极", "源极", "漏极", "沟道",
        ],
        "graph_confirm": None,
    },
    "gradient_descent": {
        "detect": [
            "gradient", "descent", "梯度下降", "学习率", "损失函数", "loss",
            "optimizer", "优化器", "反向传播",
        ],
        "graph_confirm": None,
    },
    "cooking": {
        "detect": [
            "cook", "cooking", "recipe", "food", "dish", "wok", "skillet",
            "stir-fry", "stir fry", "sauce", "tofu", "mapo",
            "麻婆", "豆腐", "烹饪", "做法", "好吃", "食材",
            "炒", "煸", "爆香", "锅", "菜", "勾芡", "出锅", "装盘",
        ],
        "graph_confirm": [
            "食材", "豆腐", "肉末", "豆瓣酱", "花椒", "蒜苗", "红油",
            "炒锅", "炒", "煸", "烧", "勾芡", "装盘",
            "wok", "tofu", "sauce", "recipe", "cook",
        ],
    },
    "math_proof": {
        "detect": [
            "证明", "推导", "积分", "求导", "微分",
            "integral", "derivative", "differential",
            "theorem", "引理", "命题", "几何证明",
            "iit", "柯西", "拉格朗日", "泰勒展开",
        ],
        "graph_confirm": None,
    },
    "marketing": {
        "detect": [
            "广告", "营销", "产品", "推广", "brand", "marketing",
            "ad ", "ads", "golpo", "landing", "品牌", "宣传",
        ],
        "graph_confirm": None,
    },
}


# Convenience exports for backward compatibility
SEMICONDUCTOR_TERMS = TOPIC_TERMS["semiconductor"]["detect"]
GRADIENT_TERMS = TOPIC_TERMS["gradient_descent"]["detect"]
COOKING_TERMS = TOPIC_TERMS["cooking"]["detect"]
COOKING_GRAPH_TERMS = TOPIC_TERMS["cooking"]["graph_confirm"]
CHALKBOARD_MATH_SIGNALS = TOPIC_TERMS["math_proof"]["detect"]
MARKETING_SIGNALS = TOPIC_TERMS["marketing"]["detect"]
