from __future__ import annotations

"""Module 4: RAGAS Evaluation — 4 metrics + failure analysis."""

import os, sys, json
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TEST_SET_PATH, GOOGLE_API_KEY


@dataclass
class EvalResult:
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float


def load_test_set(path: str = TEST_SET_PATH) -> list[dict]:
    """Load test set from JSON. (Đã implement sẵn)"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def evaluate_ragas(questions: list[str], answers: list[str],
                   contexts: list[list[str]], ground_truths: list[str]) -> dict:
    """Run RAGAS evaluation."""
    zeros = {"faithfulness": 0.0, "answer_relevancy": 0.0,
             "context_precision": 0.0, "context_recall": 0.0, "per_question": []}
    try:
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        from datasets import Dataset

        from ragas.run_config import RunConfig

        _google_base = "https://generativelanguage.googleapis.com/v1beta/openai/"
        llm = LangchainLLMWrapper(ChatOpenAI(
            model="gemini-2.5-flash-lite",
            openai_api_base=_google_base,
            openai_api_key=GOOGLE_API_KEY,
            max_retries=6,
        ))
        emb = LangchainEmbeddingsWrapper(OpenAIEmbeddings(
            # Qua OpenAI-compat layer của Google, model embedding cần prefix "models/"
            # (khác với chat model dùng tên trần như "gemini-2.5-flash-lite").
            model="models/gemini-embedding-001",
            openai_api_base=_google_base,
            openai_api_key=GOOGLE_API_KEY,
            chunk_size=1,                    # endpoint không hỗ trợ batch embedding
            tiktoken_enabled=False,          # tiktoken pre-tokenize thành token IDs → 501 trên endpoint này
            check_embedding_ctx_length=False,# tránh fallback dùng AutoTokenizer của HuggingFace
            max_retries=6,
        ))

        for metric in [faithfulness, answer_relevancy, context_precision, context_recall]:
            metric.llm = llm
        answer_relevancy.embeddings = emb

        dataset = Dataset.from_dict({
            "question": questions, "answer": answers,
            "contexts": contexts, "ground_truth": ground_truths,
        })
        # Gemini free-tier rate limit thấp hơn nhiều so với mặc định 16 workers của RAGAS
        # → giảm concurrency để tránh hàng loạt lỗi 503 (high demand).
        run_config = RunConfig(max_workers=3, max_retries=6, max_wait=30, timeout=180)
        result = evaluate(dataset, metrics=[faithfulness, answer_relevancy,
                                            context_precision, context_recall],
                           run_config=run_config)
        df = result.to_pandas()
        per_question = [EvalResult(
            question=row["question"], answer=row["answer"],
            contexts=row["contexts"], ground_truth=row["ground_truth"],
            faithfulness=float(row.get("faithfulness", 0.0)),
            answer_relevancy=float(row.get("answer_relevancy", 0.0)),
            context_precision=float(row.get("context_precision", 0.0)),
            context_recall=float(row.get("context_recall", 0.0)))
            for _, row in df.iterrows()]
        return {
            "faithfulness": float(df["faithfulness"].mean()),
            "answer_relevancy": float(df["answer_relevancy"].mean()),
            "context_precision": float(df["context_precision"].mean()),
            "context_recall": float(df["context_recall"].mean()),
            "per_question": per_question,
        }
    except Exception as e:
        print(f"  ⚠️  RAGAS evaluation failed: {e}")
        return zeros


def failure_analysis(eval_results: list[EvalResult], bottom_n: int = 10) -> list[dict]:
    """Analyze bottom-N worst questions using Diagnostic Tree."""
    diagnostic_tree = {
        "faithfulness": ("LLM hallucinating", "Tighten prompt, lower temperature"),
        "context_recall": ("Missing relevant chunks", "Improve chunking or add BM25"),
        "context_precision": ("Too many irrelevant chunks", "Add reranking or metadata filter"),
        "answer_relevancy": ("Answer doesn't match question", "Improve prompt template"),
    }
    scored = []
    for r in eval_results:
        metrics = {
            "faithfulness": r.faithfulness,
            "context_recall": r.context_recall,
            "context_precision": r.context_precision,
            "answer_relevancy": r.answer_relevancy,
        }
        avg = sum(metrics.values()) / len(metrics)
        worst_metric = min(metrics, key=metrics.get)
        diagnosis, suggested_fix = diagnostic_tree[worst_metric]
        scored.append({
            "question": r.question,
            "worst_metric": worst_metric,
            "score": round(avg, 4),
            "diagnosis": diagnosis,
            "suggested_fix": suggested_fix,
        })
    scored.sort(key=lambda x: x["score"])
    return scored[:bottom_n]


def save_report(results: dict, failures: list[dict], path: str = "ragas_report.json"):
    """Save evaluation report to JSON. (Đã implement sẵn)"""
    report = {
        "aggregate": {k: v for k, v in results.items() if k != "per_question"},
        "num_questions": len(results.get("per_question", [])),
        "failures": failures,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Report saved to {path}")


if __name__ == "__main__":
    test_set = load_test_set()
    print(f"Loaded {len(test_set)} test questions")
    print("Run pipeline.py first to generate answers, then call evaluate_ragas().")
