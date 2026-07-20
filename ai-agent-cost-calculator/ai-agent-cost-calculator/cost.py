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
NOVA_LITE_INPUT_COST_PER_1K = 0.00006    # Bedrock Nova Lite, per 1K input tokens
NOVA_LITE_OUTPUT_COST_PER_1K = 0.00024   # Bedrock Nova Lite, per 1K output tokens
LAMBDA_COST_PER_GB_SECOND = 0.0000166667  # Lambda compute, per GB-second
S3_GET_COST = 0.0000004                  # per GET request
S3_PUT_COST = 0.000005                   # per PUT request
GATEWAY_COST_PER_INVOCATION = 0.0001     # AgentCore Gateway, per invocation (estimate)
RUNTIME_COST_ESTIMATE = 0.0002           # AgentCore Runtime, per request (estimate)


@dataclass
class Request:
    """Everything about a single request that drives its cost."""

    pages: int                    # PDF pages sent to Textract
    input_tokens: int             # Bedrock input tokens (all translate calls)
    output_tokens: int            # Bedrock output tokens (all translate calls)
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

    bedrock_total = _round(
        req.input_tokens / 1000 * NOVA_LITE_INPUT_COST_PER_1K
        + req.output_tokens / 1000 * NOVA_LITE_OUTPUT_COST_PER_1K,
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
            "model": "amazon.nova-lite",
            "inputTokens": req.input_tokens,
            "outputTokens": req.output_tokens,
            "inputCostPer1K": NOVA_LITE_INPUT_COST_PER_1K,
            "outputCostPer1K": NOVA_LITE_OUTPUT_COST_PER_1K,
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
            "Bedrock (Nova Lite)",
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
    p.add_argument("--json", action="store_true", help="Output raw JSON instead of a report")
    return p


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    req = Request(
        pages=args.pages,
        input_tokens=args.input_tokens,
        output_tokens=args.output_tokens,
        lambda_memory_mb=args.lambda_memory_mb,
        lambda_duration_ms=args.lambda_duration_ms,
        s3_get_requests=args.s3_get_requests,
        s3_put_requests=args.s3_put_requests,
        gateway_invocations=args.gateway_invocations,
    )
    costs = calculate_cost(req)
    if args.json:
        print(json.dumps(costs, indent=2))
    else:
        print(format_report(costs))


if __name__ == "__main__":
    main()
