# AI Agent Cost Calculator

A tiny, self-contained example of how to calculate the **per-request AWS cost**
of an AI agent workload — here, a PDF translation pipeline.

No AWS account, no deployment, no dependencies. Just Python and arithmetic.

## The idea

Each request flows through a few AWS services. You price each one from its
usage, then sum:

| Service | What drives the cost | Rate |
|---|---|---|
| Textract | pages | $0.0015 / page |
| Bedrock (Nova Lite) | input + output tokens | $0.00006 / $0.00024 per 1K |
| Lambda | GB-seconds (memory × time) | $0.0000166667 / GB-s |
| S3 | GET + PUT requests | $0.0000004 / $0.000005 |
| AgentCore Gateway | invocations (est.) | $0.0001 / call |
| AgentCore Runtime | per request (est.) | $0.0002 |

All rates live at the top of [`cost.py`](cost.py) — edit them for your region.

## Usage

```bash
# Default example request
python cost.py

# A 10-page doc with more tokens
python cost.py --pages 10 --input-tokens 12000 --output-tokens 9000

# Raw JSON (e.g. to feed a dashboard)
python cost.py --pages 5 --json
```

Example output:

```
Per-request cost breakdown
==================================
Textract               $0.004500     3 pages
Bedrock (Nova Lite)    $0.001200     4000 in / 4000 out tokens
Lambda                 $0.000049     2.9297 GB-s
S3                     $0.000017     4 GET / 3 PUT
AgentCore Gateway      $0.000300     3 invocations (est.)
AgentCore Runtime      $0.000200     estimate
----------------------------------
TOTAL                  $0.006266
```

## As a library

```python
from cost import Request, calculate_cost

costs = calculate_cost(Request(pages=3, input_tokens=4000, output_tokens=4000))
print(costs["totalEstimated"])
```

## Tests

```bash
python test_cost.py        # or: python -m pytest
```
