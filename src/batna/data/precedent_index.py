"""Hybrid Precedent Retrieval Index combining BM25, semantic vector embeddings, and RRF."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from batna.data.usaspending import ProcurementAward


def simple_tokenize(text: str) -> list[str]:
    """Lowercase whitespace/punctuation tokenizer."""
    return re.findall(r"\w+", text.lower())


class SimpleBM25:
    """In-memory BM25 implementation for lexical keyword retrieval over documents."""

    def __init__(
        self,
        corpus: list[list[str]],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.corpus = corpus
        self.k1 = k1
        self.b = b
        self.corpus_size: int = len(corpus)
        self.doc_lens: list[int] = [len(doc) for doc in corpus]
        self.avg_doc_len: float = (
            sum(self.doc_lens) / self.corpus_size if self.corpus_size > 0 else 1.0
        )
        self.doc_freqs: dict[str, int] = Counter()
        self.doc_term_freqs: list[Counter[str]] = []

        for doc in corpus:
            term_freq = Counter(doc)
            self.doc_term_freqs.append(term_freq)
            for term in term_freq:
                self.doc_freqs[term] += 1

        self.idf: dict[str, float] = {}
        for term, freq in self.doc_freqs.items():
            # Standard Lucene/BM25 IDF
            self.idf[term] = math.log(
                (self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0
            )

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        """Calculate BM25 relevance score for each document against query."""
        scores = [0.0] * self.corpus_size
        for term in query_tokens:
            if term not in self.idf:
                continue
            term_idf = self.idf[term]
            for doc_idx, term_freqs in enumerate(self.doc_term_freqs):
                tf = term_freqs.get(term, 0)
                if tf == 0:
                    continue
                doc_len = self.doc_lens[doc_idx]
                denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
                scores[doc_idx] += term_idf * (tf * (self.k1 + 1.0) / denom)
        return scores


@dataclass
class SearchResult:
    """Ranked search result with provenance metadata and real pricing values."""

    award: ProcurementAward
    score: float
    bm25_rank: int | None
    vector_rank: int | None
    rrf_score: float


class PrecedentHybridIndex:
    """
    Hybrid retrieval index combining BM25 lexical ranking and dense TF-IDF/semantic
    vector similarity, fused via Reciprocal Rank Fusion (RRF).
    """

    def __init__(self, awards: list[ProcurementAward], rrf_k: int = 60) -> None:
        self.awards = awards
        self.rrf_k = rrf_k

        # Document representations combining title, description, agency, and vendor
        self.doc_texts: list[str] = [
            f"{a.recipient_name} {a.awarding_agency} {a.description} {a.naics_code or ''}"
            for a in awards
        ]

        # 1. Lexical Index (BM25)
        tokenized_corpus = [simple_tokenize(text) for text in self.doc_texts]
        self.bm25 = SimpleBM25(tokenized_corpus)

        # 2. Dense Vector Index (TF-IDF sublinear vectorizer for pure Python/scikit-learn stability)
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            sublinear_tf=True,
            max_features=10000,
        )
        if self.doc_texts:
            self.doc_vectors = self.vectorizer.fit_transform(self.doc_texts)
        else:
            self.doc_vectors = None

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_amount: float | None = None,
        max_amount: float | None = None,
    ) -> list[SearchResult]:
        """Perform hybrid retrieval with Reciprocal Rank Fusion and optional budget constraints."""
        if not self.awards or self.doc_vectors is None:
            return []

        # 1. BM25 Scores & Ranking
        query_tokens = simple_tokenize(query)
        bm25_scores = self.bm25.get_scores(query_tokens)
        bm25_sorted_indices = sorted(
            range(len(bm25_scores)), key=lambda idx: bm25_scores[idx], reverse=True
        )
        bm25_rank_map: dict[int, int] = {
            doc_idx: rank + 1 for rank, doc_idx in enumerate(bm25_sorted_indices)
        }

        # 2. Vector Cosine Similarity & Ranking
        query_vec = self.vectorizer.transform([query])
        cosine_sims = cosine_similarity(query_vec, self.doc_vectors)[0]
        vector_sorted_indices = sorted(
            range(len(cosine_sims)), key=lambda idx: cosine_sims[idx], reverse=True
        )
        vector_rank_map: dict[int, int] = {
            doc_idx: rank + 1 for rank, doc_idx in enumerate(vector_sorted_indices)
        }

        # 3. Reciprocal Rank Fusion (RRF)
        # RRF score = 1 / (k + rank_bm25) + 1 / (k + rank_vector)
        rrf_scores: dict[int, float] = {}
        for idx in range(len(self.awards)):
            # Filter by deal amount if specified
            amount = self.awards[idx].award_amount
            if min_amount is not None and amount < min_amount:
                continue
            if max_amount is not None and amount > max_amount:
                continue

            r_bm25 = bm25_rank_map[idx]
            r_vec = vector_rank_map[idx]

            rrf = (1.0 / (self.rrf_k + r_bm25)) + (1.0 / (self.rrf_k + r_vec))
            rrf_scores[idx] = rrf

        # Sort by RRF score
        sorted_rrf = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)[
            :top_k
        ]

        results: list[SearchResult] = []
        for doc_idx, score in sorted_rrf:
            results.append(
                SearchResult(
                    award=self.awards[doc_idx],
                    score=score,
                    bm25_rank=bm25_rank_map.get(doc_idx),
                    vector_rank=vector_rank_map.get(doc_idx),
                    rrf_score=score,
                )
            )

        return results

    def to_mcp_format(self, results: list[SearchResult]) -> list[dict[str, Any]]:
        """Format search results for MCP tool responses."""
        return [
            {
                "award_id": r.award.award_id,
                "vendor": r.award.recipient_name,
                "agency": r.award.awarding_agency,
                "amount": r.award.award_amount,
                "description": r.award.description,
                "dates": f"{r.award.start_date or 'N/A'} to {r.award.end_date or 'N/A'}",
                "relevance_rrf_score": round(r.rrf_score, 5),
                "source_url": r.award.source_url,
            }
            for r in results
        ]
