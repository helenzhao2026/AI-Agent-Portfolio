"""Unit economics of an AI agent: per-request AWS cost calculator.

This is a stripped-down, no-AWS version of a PDF-translation agent demo. It keeps
only the interesting part: how you turn a request's resource usage (pages,
tokens, Lambda time) into a dollar cost, itemised by service.

The pipeline being priced has three steps, each historically a Lambda:
    1. extract   - Textract reads text blocks from the PDF
    2. translate - Bedrock (Nova Lite) translates the blocks
    3. save       - rebuild the translated PDF

Run `python cost.py --help` for the CLI.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Pricing constants (USD). Update these to your region / current AWS pricing.
# --------------------------------------------------------------------------- #
TEXTRACT_COST_PER_PAGE = 0.0015          # AnalyzeDocument LAYOUT, per page
LAMBDA_COST_PER_GB_SECOND = 0.0000166667  # Lambda compute, per GB-second
S3_GET_COST = 0.0000004                  # per GET request
S3_PUT_COST = 0.000005                   # per PUT request
GATEWAY_COST_PER_INVOCATION = 0.0001     # AgentCore Gateway, per invocation (estimate)
RUNTIME_COST_ESTIMATE = 0.0002           # AgentCore Runtime, per request (estimate)

# Bedrock model pricing, USD per 1,000 tokens (input, output).
# APPROXIMATE / illustrative — confirm against current Bedrock pricing for your
# region before quoting real numbers. The whole point of the comparison is that
# model choice, not infrastructure, dominates the bill.
MODELS = {
    "nova-micro": {"input": 0.000035, "output": 0.00014},
    "nova-lite": {"input": 0.00006, "output": 0.00024},
    "nova-pro": {"input": 0.0008, "output": 0.0032},
    "claude-haiku": {"input": 0.0008, "output": 0.004},
    "claude-sonnet": {"input": 0.003, "output": 0.015},
}
DEFAULT_MODEL = "nova-lite"

# Back-compat aliases (used by earlier code / tests).
NOVA_LITE_INPUT_COST_PER_1K = MODELS["nova-lite"]["input"]
NOVA_LITE_OUTPUT_COST_PER_1K = MODELS["nova-lite"]["output"]


@dataclass
class Request:
    """Everything about a single request that drives its cost."""

    pages: int                    # PDF pages sent to Textract
    input_tokens: int             # Bedrock input tokens (all translate calls)
    output_tokens: int            # Bedrock output tokens (all translate calls)
    model: str = DEFAULT_MODEL    # which Bedrock model translates the blocks
    lambda_memory_mb: int = 1024  # memory configured for the Lambdas
    lambda_duration_ms: float = 3000.0  # total Lambda wall-clock across all 3 steps
    s3_get_requests: int = 4      # GETs across the pipeline
    s3_put_requests: int = 3      # PUTs across the pipeline
    gateway_invocations: int = 3  # AgentCore Gateway calls


def _round(value: float, places: int) -> float:
    return round(value, places)


def calculate_cost(req: Request) -> dict:
    """Return an itemised cost breakdown for one request, plus the total."""

    textract_total = _round(req.pages * TEXTRACT_COST_PER_PAGE, 6)

    if req.model not in MODELS:
        raise ValueError(f"unknown model {req.model!r}; choose from {list(MODELS)}")
    rate = MODELS[req.model]
    bedrock_total = _round(
        req.input_tokens / 1000 * rate["input"]
        + req.output_tokens / 1000 * rate["output"],
        6,
    )

    gb_seconds = (req.lambda_memory_mb / 1024) * (req.lambda_duration_ms / 1000)
    lambda_total = _round(gb_seconds * LAMBDA_COST_PER_GB_SECOND, 8)

    s3_total = _round(
        req.s3_get_requests * S3_GET_COST + req.s3_put_requests * S3_PUT_COST, 8
    )

    gateway_total = _round(req.gateway_invocations * GATEWAY_COST_PER_INVOCATION, 6)
    runtime_total = RUNTIME_COST_ESTIMATE

    costs = {
        "textract": {
            "pages": req.pages,
            "costPerPage": TEXTRACT_COST_PER_PAGE,
            "total": textract_total,
        },
        "bedrock": {
            "model": req.model,
            "inputTokens": req.input_tokens,
            "outputTokens": req.output_tokens,
            "inputCostPer1K": rate["input"],
            "outputCostPer1K": rate["output"],
            "total": bedrock_total,
        },
        "lambda": {
            "memoryMb": req.lambda_memory_mb,
            "durationMs": round(req.lambda_duration_ms),
            "gbSeconds": _round(gb_seconds, 4),
            "costPerGbSecond": LAMBDA_COST_PER_GB_SECOND,
            "total": lambda_total,
        },
        "s3": {
            "getRequests": req.s3_get_requests,
            "putRequests": req.s3_put_requests,
            "total": s3_total,
        },
        "agentcoreGateway": {
            "invocations": req.gateway_invocations,
            "costPerInvocation": GATEWAY_COST_PER_INVOCATION,
            "total": gateway_total,
            "note": "estimate",
        },
        "agentcoreRuntime": {
            "total": runtime_total,
            "note": "estimate",
        },
    }

    costs["totalEstimated"] = _round(
        textract_total
        + bedrock_total
        + lambda_total
        + s3_total
        + gateway_total
        + runtime_total,
        6,
    )

    return costs


def format_report(costs: dict) -> str:
    """Human-readable itemised report."""
    lines = ["", "Per-request cost breakdown", "=" * 34]
    rows = [
        ("Textract", costs["textract"]["total"], f'{costs["textract"]["pages"]} pages'),
        (
            f'Bedrock ({costs["bedrock"]["model"]})',
            costs["bedrock"]["total"],
            f'{costs["bedrock"]["inputTokens"]} in / {costs["bedrock"]["outputTokens"]} out tokens',
        ),
        (
            "Lambda",
            costs["lambda"]["total"],
            f'{costs["lambda"]["gbSeconds"]} GB-s',
        ),
        (
            "S3",
            costs["s3"]["total"],
            f'{costs["s3"]["getRequests"]} GET / {costs["s3"]["putRequests"]} PUT',
        ),
        (
            "AgentCore Gateway",
            costs["agentcoreGateway"]["total"],
            f'{costs["agentcoreGateway"]["invocations"]} invocations (est.)',
        ),
        ("AgentCore Runtime", costs["agentcoreRuntime"]["total"], "estimate"),
    ]
    for name, total, detail in rows:
        lines.append(f"{name:<22} ${total:<12.6f} {detail}")
    lines.append("-" * 34)
    lines.append(f'{"TOTAL":<22} ${costs["totalEstimated"]:<12.6f}')
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Model comparison
# --------------------------------------------------------------------------- #
from dataclasses import replace  # noqa: E402


def compare_models(req: Request, models: list[str] | None = None) -> list[dict]:
    """Price the *same* request across several Bedrock models.

    Returns a list of {model, bedrock, total} sorted cheapest-first. Shows that
    the model you pick, not the plumbing, is what moves the total.
    """
    models = models or list(MODELS)
    rows = []
    for m in models:
        costs = calculate_cost(replace(req, model=m))
        rows.append(
            {
                "model": m,
                "bedrock": costs["bedrock"]["total"],
                "total": costs["totalEstimated"],
            }
        )
    return sorted(rows, key=lambda r: r["total"])


def format_comparison(rows: list[dict]) -> str:
    lines = ["", "Same request, different models", "=" * 44]
    lines.append(f'{"model":<16}{"bedrock":>12}{"total/req":>14}')
    lines.append("-" * 44)
    for r in rows:
        lines.append(f'{r["model"]:<16}${r["bedrock"]:>10.6f}${r["total"]:>12.6f}')
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Margin / break-even
# --------------------------------------------------------------------------- #
def margin(cost_per_request: float, price_per_request: float,
           fixed_monthly: float = 0.0) -> dict:
    """Simple unit-economics: profit, margin %, and break-even volume.

    cost_per_request  - what one request costs you (e.g. costs["totalEstimated"])
    price_per_request - what you charge for it
    fixed_monthly     - fixed monthly overhead to cover (optional)
    """
    profit = price_per_request - cost_per_request
    margin_pct = (profit / price_per_request * 100) if price_per_request else 0.0
    if profit > 0:
        breakeven = fixed_monthly / profit if fixed_monthly else 0.0
    else:
        breakeven = float("inf")  # never breaks even at this price
    return {
        "costPerRequest": round(cost_per_request, 6),
        "pricePerRequest": round(price_per_request, 6),
        "profitPerRequest": round(profit, 6),
        "marginPct": round(margin_pct, 2),
        "fixedMonthly": fixed_monthly,
        "breakevenRequests": (
            breakeven if breakeven == float("inf") else int(-(-breakeven // 1))
        ),
    }


def format_margin(m: dict) -> str:
    be = m["breakevenRequests"]
    be_str = "never (priced below cost)" if be == float("inf") else f"{be:,} requests/mo"
    return "\n".join(
        [
            "",
            "Unit economics",
            "=" * 34,
            f'Cost / request    ${m["costPerRequest"]:.6f}',
            f'Price / request   ${m["pricePerRequest"]:.6f}',
            f'Profit / request  ${m["profitPerRequest"]:.6f}',
            f'Gross margin      {m["marginPct"]:.2f}%',
            f'Fixed monthly     ${m["fixedMonthly"]:.2f}',
            f'Break-even        {be_str}',
            "",
        ]
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Estimate the per-request AWS cost of an AI agent PDF translation."
    )
    p.add_argument("--pages", type=int, default=3, help="PDF pages (Textract)")
    p.add_argument("--input-tokens", type=int, default=4000, help="Bedrock input tokens")
    p.add_argument("--output-tokens", type=int, default=4000, help="Bedrock output tokens")
    p.add_argument("--lambda-memory-mb", type=int, default=1024)
    p.add_argument("--lambda-duration-ms", type=float, default=3000.0)
    p.add_argument("--s3-get-requests", type=int, default=4)
    p.add_argument("--s3-put-requests", type=int, default=3)
    p.add_argument("--gateway-invocations", type=int, default=3)
    p.add_argument("--model", default=DEFAULT_MODEL, choices=list(MODELS),
                   help="Bedrock model used for translation")
    p.add_argument("--price", type=float, default=None,
                   help="Price you charge per request; prints unit economics")
    p.add_argument("--fixed-monthly", type=float, default=0.0,
                   help="Fixed monthly overhead for break-even (used with --price)")
    p.add_argument("--compare-models", action="store_true",
                   help="Price this request across every model instead")
    p.add_argument("--json", action="store_true", help="Output raw JSON instead of a report")
    return p


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    req = Request(
        pages=args.pages,
        input_tokens=args.input_tokens,
        output_tokens=args.output_tokens,
        model=args.model,
        lambda_memory_mb=args.lambda_memory_mb,
        lambda_duration_ms=args.lambda_duration_ms,
        s3_get_requests=args.s3_get_requests,
        s3_put_requests=args.s3_put_requests,
        gateway_invocations=args.gateway_invocations,
    )

    if args.compare_models:
        rows = compare_models(req)
        print(json.dumps(rows, indent=2) if args.json else format_comparison(rows))
        return

    costs = calculate_cost(req)
    if args.json:
        print(json.dumps(costs, indent=2))
    else:
        print(format_report(costs))

    if args.price is not None:
        m = margin(costs["totalEstimated"], args.price, args.fixed_monthly)
        print(json.dumps(m, indent=2) if args.json else format_margin(m))


if __name__ == "__main__":
    main()
