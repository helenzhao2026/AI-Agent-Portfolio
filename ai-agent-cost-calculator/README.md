# AI Agent Cost Calculator

Built a unit-economics model for a multi-step AI agent pipeline (document extraction → LLM translation → storage), with per-service cost breakdown, model comparison, and margin analysis.

This is a tiny, self-contained example of how to calculate the **per-request AWS cost**
of an AI agent workload — here, a PDF translation pipeline.

The repo has two halves:

1. **`cost.py`** — price the pipeline (no AWS account needed)
2. **`agent.py`** — run the pipeline: extract text → translate → save PDF

## Quick start (agent demo)

```bash
pip install -r requirements.txt

# Offline demo — no API keys, uses a mock translator
python agent.py --demo --backend mock

# With cost estimate for the run you just did
python agent.py --demo --backend mock --estimate-cost

# Real translation (pick one backend)
python agent.py input.pdf --backend bedrock --target-lang Spanish
python agent.py input.pdf --backend ollama --target-lang Spanish
python agent.py input.pdf --backend auto    # bedrock → ollama → mock
```

The agent writes `<input>_translated.pdf` (or use `-o out.pdf`).

| Backend | Needs |
|---|---|
| `mock` | nothing — prefixes text with `[SPANISH demo translation]` |
| `ollama` | [Ollama](https://ollama.com) running locally (`ollama serve`) |
| `bedrock` | AWS credentials + Bedrock model access |
| `auto` | tries bedrock, then ollama, then mock |

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
The Bedrock model prices are in the `MODELS` table there.

## Usage

```bash
# Default example request
python cost.py

# A 10-page doc with more tokens, on a different model
python cost.py --pages 10 --input-tokens 12000 --output-tokens 9000 --model nova-pro

# Price the SAME request across every model (model choice dominates the bill)
python cost.py --compare-models

# Unit economics: margin + break-even at a given price
python cost.py --price 0.02 --fixed-monthly 100

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
from cost import Request, calculate_cost, compare_models, margin

req = Request(pages=3, input_tokens=4000, output_tokens=4000)

costs = calculate_cost(req)
print(costs["totalEstimated"])

# Same request, every model, cheapest first
for row in compare_models(req):
    print(row["model"], row["total"])

# Margin at a $0.02 price with $100/mo fixed overhead
print(margin(costs["totalEstimated"], 0.02, fixed_monthly=100))
```

## Charts & notebook

[`charts.py`](charts.py) has matplotlib charts (cost breakdown, monthly
projection, model comparison), and [`cost_walkthrough.ipynb`](cost_walkthrough.ipynb)
walks through the whole model with those charts inline.

```bash
pip install -r requirements.txt
jupyter notebook cost_walkthrough.ipynb
```

```python
import cost, charts
charts.model_comparison(cost.compare_models(req)).savefig("models.png", dpi=150)
```

## Tests

```bash
python test_cost.py        # cost calculator
python test_agent.py       # PDF agent (mock backend)
python -m pytest           # both, if pytest is installed
```
