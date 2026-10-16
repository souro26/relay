"""Prompt templates for order change natural language interpretation."""

from string import Template

# System prompt for order change interpretation
SYSTEM_PROMPT = (
    "You are an expert at interpreting natural language requests to "
    "modify order delivery dates. "
    "Your task is to extract structured information from the user's "
    "request and output it as valid JSON.\n\n"
    "You must extract:\n"
    '1. order_id: The order identifier (e.g., "ORD-9D3220DE", '
    '"order #12345", "order ABC-123")\n'
    "2. requested_delivery_date: The new delivery date in ISO 8601 "
    "format (YYYY-MM-DD)\n"
    "3. customer_id (optional): Customer ID if explicitly mentioned\n\n"
    "Rules:\n"
    "- If the order ID is ambiguous or missing, include it in the "
    '"missing_fields" or "ambiguities" list\n'
    '- If the date is ambiguous (e.g., "next Friday", "next week"), '
    'include it in "ambiguities" with suggestions\n'
    '- If the date is missing, include "requested_delivery_date" in '
    "missing_fields\n"
    '- If the order ID is missing, include "order_id" in '
    "missing_fields\n"
    '- Parse dates flexibly: "November 22, 2026", "Nov 22 2026", '
    '"22 Nov 2026", "2026-11-22", "next Friday", "in 3 days"\n'
    "- For relative dates, calculate from the current date and provide "
    "ISO format\n"
    '- If the date is ambiguous (e.g., "next Friday" could mean this '
    "week or next), include in ambiguities\n"
    "- Always output valid JSON matching the schema\n"
    '- Set "success" to true only if ALL required fields '
    "(order_id, requested_delivery_date) are present and unambiguous\n"
    '- Set "success" to false if any required field is missing or '
    "ambiguous"
)

# Few-shot examples for few-shot prompting
FEW_SHOT_EXAMPLES = [
    {
        "input": "Change order ORD-9D3220DE's delivery date to November 22, 2026.",
        "output": {
            "success": True,
            "draft": {
                "order_id": "ORD-9D3220DE",
                "requested_delivery_date": "2026-11-22T00:00:00+00:00",
                "customer_id": None,
            },
            "missing_fields": [],
            "ambiguities": [],
            "error": None,
            "error_code": None,
        },
    },
    {
        "input": "Change order ORD-123's delivery date to next Friday",
        "output": {
            "success": False,
            "draft": {
                "order_id": "ORD-123",
                "requested_delivery_date": "2026-11-20T00:00:00+00:00",
                "customer_id": None,
            },
            "missing_fields": [],
            "ambiguities": [
                {
                    "field": "requested_delivery_date",
                    "message": ("'next Friday' is ambiguous - could mean this week or next week"),
                    "suggestions": ["2026-11-20", "2026-11-27"],
                }
            ],
            "error": "Ambiguous delivery date",
            "error_code": "AMBIGUOUS_REQUEST",
        },
    },
    {
        "input": "Please change the delivery date for order ORD-ABC123 to next week",
        "output": {
            "success": False,
            "draft": {
                "order_id": "ORD-ABC123",
                "requested_delivery_date": "2026-11-23T00:00:00+00:00",
                "customer_id": None,
            },
            "missing_fields": [],
            "ambiguities": [
                {
                    "field": "requested_delivery_date",
                    "message": ("'next week' is ambiguous - which specific day?"),
                    "suggestions": ["2026-11-23", "2026-11-24", "2026-11-25"],
                }
            ],
            "error": "Ambiguous delivery date",
            "error_code": "AMBIGUOUS_REQUEST",
        },
    },
    {
        "input": "Change delivery date to December 1st",
        "output": {
            "success": False,
            "draft": None,
            "missing_fields": ["order_id"],
            "ambiguities": [],
            "error": "Missing required field: order_id",
            "error_code": "VALIDATION_ERROR",
        },
    },
    {
        "input": "Change order ORD-456 delivery to 2026-12-25 for customer CUST-789",
        "output": {
            "success": True,
            "draft": {
                "order_id": "ORD-456",
                "requested_delivery_date": "2026-12-25T00:00:00+00:00",
                "customer_id": "CUST-789",
            },
            "missing_fields": [],
            "ambiguities": [],
            "error": None,
            "error_code": None,
        },
    },
    {
        "input": "Please change the delivery for order #12345 to Dec 25th",
        "output": {
            "success": True,
            "draft": {
                "order_id": "12345",
                "requested_delivery_date": "2026-12-25T00:00:00+00:00",
                "customer_id": None,
            },
            "missing_fields": [],
            "ambiguities": [],
            "error": None,
            "error_code": None,
        },
    },
]

# Template for building the full prompt
PROMPT_TEMPLATE = Template(
    """$system_prompt

Examples:
$examples

Current date: $current_date

User request: $user_text

Respond with valid JSON only.""".strip()
)


def build_prompt(user_text: str, current_date: str = None) -> str:
    """Build the complete prompt for the LLM."""
    from datetime import datetime

    if current_date is None:
        current_date = datetime.now().strftime("%Y-%m-%d")

    examples_text = ""
    for i, ex in enumerate(FEW_SHOT_EXAMPLES, 1):
        examples_text += f"\nExample {i}:\nInput: {ex['input']}\nOutput: {ex['output']}\n"

    return PROMPT_TEMPLATE.substitute(
        system_prompt=SYSTEM_PROMPT,
        examples=examples_text,
        current_date=current_date,
        user_text=user_text,
    )


def get_response_schema() -> dict:
    """Return the JSON schema for structured output."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "order_change_interpretation",
            "schema": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "draft": {
                        "type": ["object", "null"],
                        "properties": {
                            "order_id": {"type": "string", "minLength": 1, "maxLength": 100},
                            "requested_delivery_date": {"type": "string", "format": "date-time"},
                            "customer_id": {
                                "type": ["string", "null"],
                                "minLength": 1,
                                "maxLength": 100,
                            },
                        },
                        "required": ["order_id", "requested_delivery_date"],
                        "additionalProperties": False,
                    },
                    "missing_fields": {"type": "array", "items": {"type": "string"}},
                    "ambiguities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "message": {"type": "string"},
                                "suggestions": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["field", "message"],
                        },
                    },
                    "error": {"type": ["string", "null"]},
                    "error_code": {"type": ["string", "null"]},
                },
                "required": [
                    "success",
                    "draft",
                    "missing_fields",
                    "ambiguities",
                    "error",
                    "error_code",
                ],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
