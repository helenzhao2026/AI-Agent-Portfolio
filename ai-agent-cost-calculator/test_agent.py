"""Tests for the PDF translation agent. Run: python test_agent.py"""

from pathlib import Path

from agent import (
    AgentResult,
    create_demo_pdf,
    estimate_run_cost,
    extract_text,
    run_agent,
    save_pdf,
    translate_pages,
)
from translator import MockTranslator


def test_create_demo_pdf_and_extract():
    path = create_demo_pdf(Path("_test_demo.pdf"))
    try:
        pages = extract_text(path)
        assert len(pages) >= 1
        assert "Hello from the AI Agent" in pages[0]
    finally:
        path.unlink(missing_ok=True)


def test_mock_translate_and_save():
    pages = ["Hello world.", "Second page."]
    translated = translate_pages(pages, "Spanish", MockTranslator())
    assert translated[0].startswith("[SPANISH demo translation]")
    assert "Hello world." in translated[0]

    out = Path("_test_out.pdf")
    try:
        save_pdf(translated, out)
        assert out.exists()
        roundtrip = extract_text(out)
        assert any("Hello world." in p for p in roundtrip)
    finally:
        out.unlink(missing_ok=True)


def test_run_agent_end_to_end():
    src = create_demo_pdf(Path("_test_run.pdf"))
    out = Path("_test_run_translated.pdf")
    try:
        result = run_agent(src, target_lang="French", output_path=out, translator=MockTranslator())
        assert isinstance(result, AgentResult)
        assert result.backend == "mock"
        assert result.page_count >= 1
        assert out.exists()
    finally:
        src.unlink(missing_ok=True)
        out.unlink(missing_ok=True)


def test_estimate_run_cost():
    result = AgentResult(
        input_path=Path("in.pdf"),
        output_path=Path("out.pdf"),
        pages=["aaaa"],
        translated=["bbbb"],
        backend="mock",
        input_tokens=1000,
        output_tokens=800,
    )
    costs = estimate_run_cost(result)
    assert costs["textract"]["pages"] == 1
    assert costs["bedrock"]["inputTokens"] == 1000
    assert costs["totalEstimated"] > 0


if __name__ == "__main__":
    test_create_demo_pdf_and_extract()
    test_mock_translate_and_save()
    test_run_agent_end_to_end()
    test_estimate_run_cost()
    print("all agent tests passed")
