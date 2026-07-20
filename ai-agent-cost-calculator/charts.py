"""Matplotlib charts for the cost model. Import these in the notebook.

    import cost, charts
    charts.cost_breakdown(cost.calculate_cost(cost.Request(3, 4000, 4000)))
    charts.monthly_projection(costs)
    charts.model_comparison(cost.compare_models(req))

Each function returns the matplotlib Figure so you can save it:
    charts.cost_breakdown(costs).savefig("breakdown.png", dpi=150)
"""

from __future__ import annotations

import matplotlib.pyplot as plt

_SERVICES = [
    ("textract", "Textract"),
    ("bedrock", "Bedrock"),
    ("lambda", "Lambda"),
    ("s3", "S3"),
    ("agentcoreGateway", "Gateway"),
    ("agentcoreRuntime", "Runtime"),
]


def cost_breakdown(costs: dict):
    """Horizontal bar of per-service cost for one request."""
    labels = [name for key, name in _SERVICES]
    values = [costs[key]["total"] for key, _ in _SERVICES]

    fig, ax = plt.subplots(figsize=(7, 3.5))
    bars = ax.barh(labels, values, color="#4C78A8")
    ax.invert_yaxis()
    ax.set_xlabel("USD per request")
    ax.set_title(f"Cost breakdown — ${costs['totalEstimated']:.6f} / request")
    for bar, v in zip(bars, values):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2,
                f" ${v:.6f}", va="center", fontsize=8)
    ax.margins(x=0.15)
    fig.tight_layout()
    return fig


def monthly_projection(costs: dict, volumes=(1_000, 10_000, 100_000, 1_000_000)):
    """Line: total monthly cost vs. request volume (log-log)."""
    per = costs["totalEstimated"]
    totals = [per * v for v in volumes]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(volumes, totals, marker="o", color="#E45756")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Requests per month")
    ax.set_ylabel("Total monthly cost (USD)")
    ax.set_title("Monthly cost vs. volume")
    for v, t in zip(volumes, totals):
        ax.annotate(f"${t:,.0f}", (v, t), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=8)
    ax.grid(True, which="both", ls=":", alpha=0.5)
    fig.tight_layout()
    return fig


def model_comparison(rows: list[dict]):
    """Grouped bars: total per request for each model (cheapest first)."""
    names = [r["model"] for r in rows]
    totals = [r["total"] for r in rows]
    bedrock = [r["bedrock"] for r in rows]
    infra = [t - b for t, b in zip(totals, bedrock)]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(names, infra, label="infra (Textract/Lambda/S3/AgentCore)",
           color="#B4B4B4")
    ax.bar(names, bedrock, bottom=infra, label="Bedrock (model)", color="#4C78A8")
    ax.set_ylabel("USD per request")
    ax.set_title("Same request, different models")
    ax.legend(fontsize=8)
    for i, t in enumerate(totals):
        ax.text(i, t, f"${t:.5f}", ha="center", va="bottom", fontsize=8)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout()
    return fig


def main():
    import argparse
    from pathlib import Path

    import cost

    parser = argparse.ArgumentParser(description="Render cost model charts.")
    parser.add_argument(
        "--save",
        metavar="DIR",
        help="Save PNGs to DIR instead of opening a window.",
    )
    args = parser.parse_args()

    req = cost.Request(pages=3, input_tokens=4000, output_tokens=4000)
    costs = cost.calculate_cost(req)
    rows = cost.compare_models(req)

    figures = [
        ("breakdown", cost_breakdown(costs)),
        ("monthly", monthly_projection(costs)),
        ("models", model_comparison(rows)),
    ]

    if args.save:
        out = Path(args.save)
        out.mkdir(parents=True, exist_ok=True)
        for name, fig in figures:
            fig.savefig(out / f"{name}.png", dpi=150)
        print(f"Saved {len(figures)} charts to {out}/")
    else:
        plt.show()


if __name__ == "__main__":
    main()
