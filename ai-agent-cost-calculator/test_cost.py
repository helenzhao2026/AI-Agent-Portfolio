"""Tiny sanity tests. Run with:  python -m pytest  (or)  python test_cost.py"""

from cost import Request, calculate_cost


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


if __name__ == "__main__":
    test_totals_add_up()
    test_textract_scales_with_pages()
    test_bedrock_token_pricing()
    print("all tests passed")
