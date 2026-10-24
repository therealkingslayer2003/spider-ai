"""Compare local chat-token counts with the configured Ollama structured call.

Run ``.venv/bin/python -m tests.rag.test_verify_thesis_chat_tokenizer_cli``.
This sends two one-token requests and writes no research data.
"""

import asyncio
from datetime import UTC, datetime

from langchain_ollama import ChatOllama

from app.api.dependencies import get_filing_chat_token_counter
from app.core.config import get_settings
from app.domain.schemas.thesis_rag import (
    FilingCorpusVersion,
    FilingResearchAnswer,
    FilingRetrievalRequest,
)
from app.llm.prompts.thesis_filing_prompt_builder import ThesisFilingPromptBuilder


async def _run() -> None:
    settings = get_settings()
    counter = get_filing_chat_token_counter()
    if counter.count_kind != "local_tokenizer":
        raise RuntimeError(
            "A matching local chat tokenizer is required for verification; "
            "see docs/thesis_rag_skeleton.md"
        )
    request = FilingRetrievalRequest(
        research_id="tokenizer-verification",
        question="What was reported net revenue for the quarter?",
        asset="EXAMPLE",
        issuer_cik="0000000001",
        as_of=datetime(2026, 7, 1, tzinfo=UTC),
        corpus=FilingCorpusVersion(corpus_id="example", index_version="example-v1"),
        top_k=2,
    )
    evidence = (
        "[E1] form=10-Q; section=Revenue; units=USD millions\n"
        "Net revenue | 2026 | 2025\nNet revenue | $9,277 | $8,064\n"
    ) * 20
    prompts = {
        "short": "Hello.",
        "structured_research": ThesisFilingPromptBuilder().build(
            task="answer", request=request, formatted_context=evidence
        ),
    }
    llm = ChatOllama(
        model=settings.ollama_chat_model,
        base_url=settings.ollama_base_url,
        temperature=settings.ollama_temperature,
        num_ctx=settings.ollama_num_ctx,
        num_predict=1,
    ).with_structured_output(FilingResearchAnswer, include_raw=True)
    print(f"model={settings.ollama_chat_model} tokenizer={counter.version}")
    for name, prompt in prompts.items():
        result = await llm.ainvoke(prompt)
        if not isinstance(result, dict):
            raise RuntimeError("Structured Ollama call did not return raw metadata")
        actual = result["raw"].response_metadata.get("prompt_eval_count")
        if not isinstance(actual, int):
            raise RuntimeError("Ollama did not report prompt_eval_count")
        local = counter.count_prompt(prompt)
        difference = actual - local
        print(f"{name}: local={local} ollama={actual} difference={difference:+d}")
        if abs(difference) > settings.thesis_rag_generation_safety_margin_tokens:
            raise RuntimeError("Chat-token difference exceeds the safety margin")


if __name__ == "__main__":
    asyncio.run(_run())
