"""
Text Utilities

Shared text processing utilities used across the codebase.
"""

import re
from typing import Any


# Term replacement map for Chinese localization
_CHINESE_LOCALIZATION_MAP: dict[str, str] = {
    "相互依赖": "互相依赖",
    "互赖": "互相依赖",
    "同理心倾听": "先理解别人",
    "协同增效": "统合综效",
    "削尖锯子": "不断更新",
}


def localize_chinese_terms(text: str) -> str:
    """Normalize Chinese terms to their preferred forms.

    Args:
        text: The input text to localize.

    Returns:
        Text with normalized Chinese terms.
    """
    result = str(text or "")
    for source, target in _CHINESE_LOCALIZATION_MAP.items():
        result = result.replace(source, target)
    return result


def clean_text(text: str) -> str:
    """Clean and normalize text by removing ANSI codes and normalizing whitespace.

    Args:
        text: The input text to clean.

    Returns:
        Cleaned text with ANSI codes removed and whitespace normalized.
    """
    # Remove ANSI color codes
    cleaned = re.sub(r"\x1b\[[0-9;]*m", "", str(text or ""))
    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def normalize_text(text: str) -> str:
    """Normalize text for comparison by removing whitespace and lowercasing.

    Args:
        text: The input text to normalize.

    Returns:
        Normalized text suitable for comparison.
    """
    return re.sub(r"\s+", "", text).lower()


def looks_corrupted(text: str) -> bool:
    """Check if text appears to be corrupted (e.g., Mojibake).

    Args:
        text: The text to check.

    Returns:
        True if the text appears corrupted.
    """
    if not text:
        return False
    question_runs = len(re.findall(r"\?{4,}", text))
    replacement_count = text.count("�")
    visible = max(1, len(re.sub(r"\s+", "", text)))
    return question_runs > 0 or replacement_count / visible > 0.01


def contains_any_text(text: str, terms: list[str]) -> bool:
    """Check if any of the given terms appear in the text (case-insensitive).

    Args:
        text: The text to search in.
        terms: List of terms to search for.

    Returns:
        True if any term is found in the text.
    """
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def as_str_list(value: Any, limit: int | None = None) -> list[str]:
    """Convert a value to a list of cleaned strings.

    Handles both list inputs and string inputs (split by newlines or delimiters).

    Args:
        value: The value to convert.
        limit: Optional maximum number of items to return.

    Returns:
        List of cleaned string values.
    """
    if isinstance(value, list):
        items = [clean_text(item) for item in value]
    elif isinstance(value, str):
        items = [clean_text(part) for part in re.split(r"[\n；;]+", value)]
    else:
        items = []

    items = [item for item in items if item]
    return items[:limit] if limit else items
