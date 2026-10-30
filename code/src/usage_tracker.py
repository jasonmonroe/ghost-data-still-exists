# src/usage_tracker.py

"""
+-----------------------------------------------------------------------------+
|                              USAGE TRACKER                                  |
+-----------------------------------------------------------------------------+

Accumulates REAL per-call token usage (from each API response's own
`usage` field, never estimated) across a single run, keyed by the model
name the provider actually reports back. This is what
evaluation/usage_report.md is built from, so it reflects the real final
full-dataset run rather than a guess.
"""

from dataclasses import dataclass, field

from src.constants import MAX_TOKENS


@dataclass
class ModelUsage:
    response_id: str | None
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    least: dict = field(
        default_factory=lambda: {
            "response_id": None,
            "tokens": MAX_TOKENS * 2,
            "prompt": "",
        }
    )

    most: dict = field(
        default_factory=lambda: {"response_id": None, "tokens": 0, "prompt": ""}
    )

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class UsageTracker:
    def __init__(self):
        self._by_model: dict[str, ModelUsage] = {}

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        prompt: str,
        response_id,
    ) -> None:
        usage = self._by_model.setdefault(model, ModelUsage())

        total_tokens = input_tokens + output_tokens
        token_data = {
            "response_id": response_id,
            "prompt": prompt,
            "tokens": total_tokens,
        }

        # Record prompt ID's and min/max token usage
        if total_tokens < usage.least["tokens"]:
            usage.least = token_data

        if total_tokens > usage.most["tokens"]:
            usage.most = token_data

        # Update the input and output tokens
        usage.response_id = response_id
        usage.calls += 1
        usage.input_tokens += input_tokens
        usage.output_tokens += output_tokens

    def by_model(self) -> dict[str, ModelUsage]:
        return dict(self._by_model)

    def totals(self) -> ModelUsage:
        overall = ModelUsage()
        for usage in self._by_model.values():
            overall.calls += usage.calls
            overall.input_tokens += usage.input_tokens
            overall.output_tokens += usage.output_tokens

        return overall
