"""Minimal PDF translation agent: extract → translate → save.

This is the runnable counterpart to the cost calculator — same pipeline,
actually implemented.

    python agent.py --demo
    python agent.py input.pdf --target-lang es --backend mock
    python agent.py input.pdf --backend bedrock --estimate-cost
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from cost import Request, calculate_cost, format_report
from translator import Translator, auto_backend, get_translator


@dataclass
class AgentResult:
    input_path: Path
    output_path: Path
    pages: list[str]
    translated: list[str]
    backend: str
    input_tokens: int
    output_tokens: int

    @property
    def page_count(self) -> int:
        return len(self.pages)


def _estimate_tokens(text: str) -> int:
    """Rough token count (~4 chars per token). Good enough for cost estimates."""
    return max(1, len(text) // 4)


def extract_text(pdf_path: Path) -> list[str]:
    """Step 1: pull one text block per page (Textract stand-in)."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Install pypdf: pip install pypdf") from exc

    reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        pages.append(text)
    if not any(pages):
        raise ValueError(f"No extractable text in {pdf_path}")
    return pages


def translate_pages(
    pages: list[str],
    target_lang: str,
    translator: Translator,
) -> list[str]:
    """Step 2: translate each page block."""
    return [translator.translate(page, target_lang) for page in pages]


def save_pdf(pages: list[str], output_path: Path, title: str = "Translated document") -> None:
    """Step 3: write translated text into a new PDF."""
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise RuntimeError("Install fpdf2: pip install fpdf2") from exc

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)

    for i, text in enumerate(pages, start=1):
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 6, f"{title} - page {i}/{len(pages)}\n\n{text}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_path))


def run_agent(
    pdf_path: Path,
    *,
    target_lang: str = "Spanish",
    output_path: Path | None = None,
    translator: Translator | None = None,
) -> AgentResult:
    """Run the full extract → translate → save pipeline."""
    pdf_path = pdf_path.resolve()
    if output_path is None:
        output_path = pdf_path.with_name(f"{pdf_path.stem}_translated.pdf")
    else:
        output_path = output_path.resolve()

    if translator is None:
        translator = auto_backend()

    pages = extract_text(pdf_path)
    translated = translate_pages(pages, target_lang, translator)
    save_pdf(translated, output_path, title=f"Translated to {target_lang}")

    input_tokens = sum(_estimate_tokens(p) for p in pages)
    output_tokens = sum(_estimate_tokens(p) for p in translated)

    return AgentResult(
        input_path=pdf_path,
        output_path=output_path,
        pages=pages,
        translated=translated,
        backend=translator.name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def estimate_run_cost(result: AgentResult, model: str = "nova-lite") -> dict:
    """Map a completed run onto the cost calculator."""
    req = Request(
        pages=result.page_count,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        model=model,
    )
    return calculate_cost(req)


def create_demo_pdf(path: Path) -> Path:
    """Write a tiny sample PDF for `--demo`."""
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise RuntimeError("Install fpdf2: pip install fpdf2") from exc

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(
        0,
        8,
        "Hello from the AI Agent Cost Calculator demo.\n\n"
        "This one-page PDF flows through three steps:\n"
        "1. Extract text from the PDF\n"
        "2. Translate with Bedrock, Ollama, or a mock backend\n"
        "3. Save a new translated PDF\n\n"
        "Run with --estimate-cost to see what this request would cost on AWS.",
    )
    pdf.output(str(path))
    return path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Minimal PDF translation agent (extract → translate → save)."
    )
    p.add_argument("pdf", nargs="?", type=Path, help="Input PDF path")
    p.add_argument(
        "--demo",
        action="store_true",
        help="Create a sample PDF and run the pipeline on it",
    )
    p.add_argument(
        "--target-lang",
        default="Spanish",
        help="Target language for translation (default: Spanish)",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output PDF path (default: <input>_translated.pdf)",
    )
    p.add_argument(
        "--backend",
        choices=("auto", "mock", "ollama", "bedrock"),
        default="auto",
        help="Translation backend (default: auto-detect)",
    )
    p.add_argument(
        "--ollama-model",
        default="llama3.2",
        help="Ollama model name when --backend ollama",
    )
    p.add_argument(
        "--bedrock-model",
        default="amazon.nova-lite-v1:0",
        help="Bedrock model ID when --backend bedrock",
    )
    p.add_argument(
        "--bedrock-region",
        default="us-east-1",
        help="AWS region for Bedrock",
    )
    p.add_argument(
        "--estimate-cost",
        action="store_true",
        help="Print an AWS cost estimate after the run (uses cost.py)",
    )
    p.add_argument(
        "--cost-model",
        default="nova-lite",
        choices=("nova-micro", "nova-lite", "nova-pro", "claude-haiku", "claude-sonnet"),
        help="Bedrock model for cost estimate (default: nova-lite)",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)

    if args.demo:
        demo_dir = Path(__file__).resolve().parent / "samples"
        pdf_path = create_demo_pdf(demo_dir / "demo.pdf")
        print(f"Created demo PDF: {pdf_path}")
    elif args.pdf is None:
        raise SystemExit("Provide a PDF path or use --demo")
    else:
        pdf_path = args.pdf

    if args.backend == "auto":
        translator = auto_backend()
    elif args.backend == "ollama":
        translator = get_translator("ollama", model=args.ollama_model)
    elif args.backend == "bedrock":
        translator = get_translator(
            "bedrock",
            model_id=args.bedrock_model,
            region=args.bedrock_region,
        )
    else:
        translator = get_translator("mock")

    result = run_agent(
        pdf_path,
        target_lang=args.target_lang,
        output_path=args.output,
        translator=translator,
    )

    print(f"Backend:   {result.backend}")
    print(f"Pages:     {result.page_count}")
    print(f"Input:     {result.input_path}")
    print(f"Output:    {result.output_path}")
    print(f"Tokens:    ~{result.input_tokens} in / ~{result.output_tokens} out (estimated)")

    if args.estimate_cost:
        costs = estimate_run_cost(result, model=args.cost_model)
        print(format_report(costs))


if __name__ == "__main__":
    main()
