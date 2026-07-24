import json
from typing import Any


def parse_llm_json(raw_output: str) -> Any:
    """Parse JSON from LLM output, tolerating Markdown fences or preambles."""
    cleaned_output = _strip_markdown_fence(raw_output.strip())

    try:
        return json.loads(cleaned_output)
    except json.JSONDecodeError:
        return _extract_first_json_value(cleaned_output)


def _strip_markdown_fence(value: str) -> str:
    if not value.startswith("```"):
        return value

    lines = value.splitlines()

    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()

    return value


def _extract_first_json_value(value: str) -> Any:
    decoder = json.JSONDecoder()

    for index, character in enumerate(value):
        if character not in "[{":
            continue

        try:
            parsed, _ = decoder.raw_decode(value[index:])
            return parsed
        except json.JSONDecodeError:
            continue

    raise json.JSONDecodeError("No JSON object or array found", value, 0)
