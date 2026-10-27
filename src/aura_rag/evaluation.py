from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .core import lexical_score


def evaluate_retrieval_fixture(
    fixture: dict[str, Any],
    retrieve: Callable[[str, list[dict[str, str]], int], list[str]],
    top_k: int = 3,
) -> dict[str, int | float]:
    documents = fixture["documents"]
    cases = fixture["questions"]
    positive_cases = [case for case in cases if case.get("expected_document_id")]
    negative_cases = [case for case in cases if not case.get("expected_document_id")]
    hits = 0
    citations = 0
    correct_citations = 0
    negative_abstentions = 0
    for case in cases:
        ranked_ids = retrieve(case["question"], documents, top_k)
        expected = case.get("expected_document_id")
        if expected:
            hits += int(expected in ranked_ids)
            citations += len(ranked_ids)
            correct_citations += sum(
                document_id == expected for document_id in ranked_ids
            )
        else:
            negative_abstentions += int(not ranked_ids)
            citations += len(ranked_ids)
    return {
        "top_k": top_k,
        "positive_question_count": len(positive_cases),
        "negative_question_count": len(negative_cases),
        "recall_at_k": hits / len(positive_cases) if positive_cases else 0.0,
        "citation_precision": correct_citations / citations if citations else 0.0,
        "negative_abstention_rate": (
            negative_abstentions / len(negative_cases) if negative_cases else 0.0
        ),
    }


def lexical_fixture_retriever(
    question: str, documents: list[dict[str, str]], limit: int,
) -> list[str]:
    ranked = [
        (lexical_score(question, document["text"]), document["id"])
        for document in documents
    ]
    ranked = [item for item in ranked if item[0] >= 0.05]
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [document_id for _, document_id in ranked[:limit]]
