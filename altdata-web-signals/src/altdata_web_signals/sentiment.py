"""FinBERT sentiment analysis utilities.

Provides batch-oriented sentiment scoring using ProsusAI/finbert.
The pipeline is lazy-loaded on first call (~420 MB download, cached by HuggingFace).
All public functions are CPU-only.
"""

from __future__ import annotations

from typing import Any

# Global singleton — lazy loaded on first call
_pipeline: Any = None


def _load_pipeline() -> Any:
    """Lazy-load the FinBERT pipeline.

    Uses ``ProsusAI/finbert`` via HuggingFace ``transformers``.
    Downloads ~420 MB on first invocation; cached in ``~/.cache/huggingface/``.
    """
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    from transformers import pipeline as hf_pipeline

    _pipeline = hf_pipeline(
        "sentiment-analysis",
        model="ProsusAI/finbert",
        tokenizer="ProsusAI/finbert",
        device=-1,
        truncation=True,
        max_length=512,
    )
    return _pipeline


def get_finbert_sentiment(
    texts: list[str],
    *,
    batch_size: int = 32,
) -> list[dict[str, Any]]:
    """Run FinBERT on a batch of texts.

    Returns one ``{"label": str, "score": float}`` dict per input text.
    Empty / whitespace-only inputs get ``{"label": "neutral", "score": 0.0}``.
    """
    pipe = _load_pipeline()
    neutral: dict[str, Any] = {"label": "neutral", "score": 0.0}
    results: list[dict[str, Any]] = [neutral.copy() for _ in texts]
    valid_indices: list[int] = []
    valid_texts: list[str] = []
    for i, text in enumerate(texts):
        if text and text.strip():
            valid_indices.append(i)
            valid_texts.append(text.strip())

    if valid_texts:
        raw_results = pipe(valid_texts, batch_size=batch_size)
        for idx, result in zip(valid_indices, raw_results, strict=True):
            results[idx] = result

    return results


def finbert_to_numeric(result: dict[str, Any]) -> float:
    """Map a single FinBERT result to **[-1, +1]**.

    * ``"positive"`` → ``+score``
    * ``"negative"`` → ``-score``
    * ``"neutral"``  → ``0.0``
    """
    label = result.get("label", "neutral").lower()
    score = float(result.get("score", 0.0))
    if label == "positive":
        return score
    if label == "negative":
        return -score
    return 0.0


def finbert_batch_numeric(texts: list[str], *, batch_size: int = 32) -> list[float]:
    """Run FinBERT and return numeric scores for every text."""
    results = get_finbert_sentiment(texts, batch_size=batch_size)
    return [finbert_to_numeric(r) for r in results]


def finbert_batch_stats(texts: list[str], *, batch_size: int = 32) -> dict[str, float | None]:
    """Compute aggregate FinBERT statistics over *texts*.

    Returns
    -------
    dict with keys ``mean``, ``std``, ``positive_ratio``,
    ``negative_ratio``, ``neg_minus_pos``.  All ``None`` when *texts*
    is empty or entirely whitespace.
    """
    clean = [t for t in texts if t and t.strip()]
    if not clean:
        return {
            "mean": None,
            "std": None,
            "positive_ratio": None,
            "negative_ratio": None,
            "neg_minus_pos": None,
        }

    results = get_finbert_sentiment(clean, batch_size=batch_size)
    numeric = [finbert_to_numeric(r) for r in results]
    labels = [r.get("label", "neutral").lower() for r in results]

    n = len(numeric)
    mean_val = sum(numeric) / n
    variance = sum((x - mean_val) ** 2 for x in numeric) / n
    std_val = variance ** 0.5

    pos_count = sum(1 for lb in labels if lb == "positive")
    neg_count = sum(1 for lb in labels if lb == "negative")

    return {
        "mean": mean_val,
        "std": std_val,
        "positive_ratio": pos_count / n,
        "negative_ratio": neg_count / n,
        "neg_minus_pos": (neg_count - pos_count) / n,
    }
