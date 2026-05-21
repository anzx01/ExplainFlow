"""
LLM Response Validation

Provides schema validation for LLM JSON responses to ensure they conform
to expected structures before processing.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when LLM response fails schema validation."""
    pass


def require_keys(data: dict, keys: list[str], context: str = "response") -> None:
    """Validate that required keys are present in the response.

    Args:
        data: The dictionary to validate.
        keys: List of required key names.
        context: Description of what is being validated (for error messages).

    Raises:
        ValidationError: If any required key is missing.
    """
    missing = [k for k in keys if k not in data]
    if missing:
        raise ValidationError(
            f"Invalid {context}: missing required fields: {missing}. "
            f"Got keys: {list(data.keys())}"
        )


def require_array(data: dict, key: str, min_length: int = 0, context: str = "response") -> list:
    """Validate that a field exists and is a non-empty array.

    Args:
        data: The dictionary to validate.
        key: The key to check.
        min_length: Minimum required array length.
        context: Description for error messages.

    Returns:
        The validated array.

    Raises:
        ValidationError: If validation fails.
    """
    if key not in data:
        raise ValidationError(f"Invalid {context}: missing '{key}' field")

    value = data[key]
    if not isinstance(value, list):
        raise ValidationError(
            f"Invalid {context}: '{key}' should be an array, got {type(value).__name__}"
        )

    if len(value) < min_length:
        raise ValidationError(
            f"Invalid {context}: '{key}' has {len(value)} items, expected at least {min_length}"
        )

    return value


def require_string(data: dict, key: str, context: str = "response") -> str:
    """Validate that a field exists and is a string.

    Args:
        data: The dictionary to validate.
        key: The key to check.
        context: Description for error messages.

    Returns:
        The validated string.

    Raises:
        ValidationError: If validation fails.
    """
    if key not in data:
        raise ValidationError(f"Invalid {context}: missing '{key}' field")

    value = data[key]
    if value is not None and not isinstance(value, str):
        raise ValidationError(
            f"Invalid {context}: '{key}' should be a string, got {type(value).__name__}"
        )

    return value or ""


def validate_graph_response(data: dict) -> dict:
    """Validate and sanitize the ExplainGraph response from LLM.

    Expected structure:
    {
        "topic": str,
        "summary": str,
        "nodes": [{"id": str, "label": str, "node_type": str, ...}, ...],
        "edges": [{"source": str, "target": str, ...}, ...],
        "key_insights": [str, ...]
    }

    Args:
        data: The raw LLM JSON response.

    Returns:
        Validated and sanitized graph data.

    Raises:
        ValidationError: If validation fails.
    """
    if not isinstance(data, dict):
        raise ValidationError(f"Expected graph response to be an object, got {type(data).__name__}")

    # Require top-level fields
    require_keys(data, ["nodes"], "graph response")
    require_string(data, "topic", "graph response")

    # Validate nodes array
    nodes = require_array(data, "nodes", min_length=1, context="graph.nodes")

    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValidationError(f"Invalid graph.nodes[{i}]: expected object, got {type(node).__name__}")
        require_keys(node, ["id", "label"], f"graph.nodes[{i}]")

    # Validate edges if present
    if "edges" in data:
        edges = data["edges"]
        if not isinstance(edges, list):
            raise ValidationError("graph.edges should be an array")
        for i, edge in enumerate(edges):
            if not isinstance(edge, dict):
                raise ValidationError(f"Invalid graph.edges[{i}]: expected object, got {type(edge).__name__}")
            require_keys(edge, ["source", "target"], f"graph.edges[{i}]")

    return data


def validate_brief_response(data: dict) -> dict:
    """Validate and sanitize the EnhancedTeachingBrief response from LLM.

    Expected structure:
    {
        "original_prompt": str,
        "audience_level": str,
        "topic_type": str,
        "learning_objectives": [str, ...],
        ...
    }

    Args:
        data: The raw LLM JSON response.

    Returns:
        Validated and sanitized brief data.

    Raises:
        ValidationError: If validation fails.
    """
    if not isinstance(data, dict):
        raise ValidationError(f"Expected brief response to be an object, got {type(data).__name__}")

    # These fields are strongly recommended but we don't fail hard
    recommended_fields = [
        "original_prompt",
        "audience_level",
        "topic_type",
        "learning_objectives",
        "core_explanation_chain",
        "must_include_points",
        "recommended_scene_outline",
    ]

    for field in recommended_fields:
        if field in data and data[field] is not None:
            if not isinstance(data[field], (str, list)):
                logger.warning(
                    "Brief field '%s' has unexpected type %s, will use fallback",
                    field,
                    type(data[field]).__name__
                )

    return data


def safe_parse_json(content: str) -> dict:
    """Safely parse JSON content from LLM response with detailed error reporting.

    Args:
        content: The raw string content.

    Returns:
        Parsed JSON as a dictionary.

    Raises:
        ValidationError: If parsing fails.
    """
    import json

    if not content or not content.strip():
        raise ValidationError("LLM returned empty response")

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        # Try to extract useful context from the error
        preview = content[:500] if len(content) > 500 else content
        raise ValidationError(
            f"Failed to parse LLM JSON response: {exc}. "
            f"Content preview: {preview!r}"
        )
