from decimal import Decimal

from extractor.pricing import estimate_cost


def test_haiku_cost_is_exact_decimal():
    # 1000 in * $0.10/M + 500 out * $0.50/M = 0.0001 + 0.00025
    assert estimate_cost("claude-haiku-5-5", 1000, 500) == Decimal("0.00035")


def test_a_million_of_each_costs_the_two_prices_added():
    assert estimate_cost("claude-haiku-5-5", 1_000_000, 1_000_000) == Decimal("0.60")


def test_stub_is_free():
    assert estimate_cost("stub", 5000, 5000) == 0


def test_unknown_model_has_no_cost_rather_than_zero():
    assert estimate_cost("mystery-model", 1000, 1000) is None
