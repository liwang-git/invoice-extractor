"""Per-token prices, in one place.

Cost in this project is an estimate: tokens reported by the API times the
price here. If the numbers below are wrong, every cost figure is wrong, so
each one carries its source.
"""

from decimal import Decimal

# USD per 1,000,000 tokens, as (input, output). Money stays Decimal.
#
# Source for the Claude models: Anthropic pricing page,
# https://platform.claude.com/docs/en/about-claude/pricing (checked 2026-10-15).
PRICE_USD_PER_MTOK = {
    # The stub makes no API call, so it costs nothing.
    "stub": (Decimal("0"), Decimal("0")),
    # Haiku 5.5, for prompts up to 100,000 tokens. Prompts over 100,000 tokens
    # are priced higher ($0.50 in / $2.50 out); our invoices are far smaller.
    # Cache reads/writes are ignored: this project doesn't use prompt caching.
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
}


def estimate_cost(model, input_tokens, output_tokens):
    """Estimated USD cost as a Decimal, or None if the model has no price.

    None (not 0) for an unknown model, so a missing price can't pass for a
    free run.
    """
    prices = PRICE_USD_PER_MTOK.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    total = Decimal(input_tokens) * input_price + Decimal(output_tokens) * output_price
    return total / Decimal(1_000_000)
