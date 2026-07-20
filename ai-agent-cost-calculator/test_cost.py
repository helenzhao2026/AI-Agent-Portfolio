"""Tiny sanity tests. Run with:  python -m pytest  (or)  python test_cost.py"""

from cost import Request, calculate_cost, compare_models, margin


def test_totals_add_up():
    costs = calculate_cost(Request(pages=3, input_tokens=4000, output_tokens=4000))
    parts = (
        costs["textract"]["total"]
        + costs["bedrock"]["total"]
        + costs["lambda"]["total"]
        + costs["s3"]["total"]
        + costs["agentcoreGateway"]["total"]
        + costs["agentcoreRuntime"]["total"]
    )
    assert abs(parts - costs["totalEstimated"]) < 1e-6


def test_textract_scales_with_pages():
    one = calculate_cost(Request(pages=1, input_tokens=0, output_tokens=0))
    ten = calculate_cost(Request(pages=10, input_tokens=0, output_tokens=0))
    assert abs(ten["textract"]["total"] - 10 * one["textract"]["total"]) < 1e-9


def test_bedrock_token_pricing():
    costs = calculate_cost(Request(pages=0, input_tokens=1000, output_tokens=1000))
    # 1K in @ 0.00006 + 1K out @ 0.00024 = 0.0003
    assert abs(costs["bedrock"]["total"] - 0.0003) < 1e-9


def test_model_choice_changes_bedrock():
    lite = calculate_cost(Request(0, 10_000, 10_000, model="nova-lite"))
    sonnet = calculate_cost(Request(0, 10_000, 10_000, model="claude-sonnet"))
    assert sonnet["bedrock"]["total"] > lite["bedrock"]["total"]


def test_compare_models_sorted_cheapest_first():
    rows = compare_models(Request(3, 4000, 4000))
    totals = [r["total"] for r in rows]
    assert totals == sorted(totals)


def test_margin_and_breakeven():
    m = margin(cost_per_request=0.006, price_per_request=0.02, fixed_monthly=100)
    assert m["profitPerRequest"] == 0.014
    assert 40 < m["marginPct"] < 100
    # $100 fixed / $0.014 profit -> ~7143 requests to break even
    assert m["breakevenRequests"] == 7143


def test_margin_below_cost_never_breaks_even():
    m = margin(cost_per_request=0.02, price_per_request=0.01, fixed_monthly=100)
    assert m["profitPerRequest"] < 0
    assert m["breakevenRequests"] == float("inf")


if __name__ == "__main__":
    test_totals_add_up()
    test_textract_scales_with_pages()
    test_bedrock_token_pricing()
    test_model_choice_changes_bedrock()
    test_compare_models_sorted_cheapest_first()
    test_margin_and_breakeven()
    test_margin_below_cost_never_breaks_even()
    print("all tests passed")
