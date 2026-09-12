"""MCP server serving real USAspending.gov procurement precedents via hybrid retrieval."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from batna.config import settings
from batna.data.precedent_index import PrecedentHybridIndex
from batna.data.usaspending import ProcurementAward, USAspendingClient

logger = logging.getLogger(__name__)


precedent_server = MCPServer(
    name="precedent",
    title="Precedent Server",
    description=(
        "Serves real U.S. federal procurement award records (USAspending.gov) as "
        "negotiation precedent via hybrid BM25 + vector + RRF retrieval."
    ),
    version="0.1.0",
)


def _load_corpus(corpus_path: Path) -> list[ProcurementAward]:
    """Load the real award corpus from the configured cache file."""
    return USAspendingClient.load_corpus_cache(corpus_path)


class PrecedentServerState:
    """Lazy, cached state for the precedent server: the loaded retrieval index."""

    def __init__(self, corpus_path: Path | None = None) -> None:
        self.corpus_path = corpus_path or Path(settings.precedent_corpus_path)
        self._index: PrecedentHybridIndex | None = None

    def get_index(self) -> PrecedentHybridIndex:
        """Load (once) and return the hybrid index over the real corpus."""
        if self._index is None:
            awards = _load_corpus(self.corpus_path)
            if not awards:
                raise RuntimeError(
                    f"Precedent corpus at {self.corpus_path} is empty. "
                    "Build it first with USAspendingClient.build_corpus_cache."
                )
            logger.info("Loaded %d real procurement awards from %s", len(awards), self.corpus_path)
            self._index = PrecedentHybridIndex(awards)
        return self._index


_state = PrecedentServerState()


@precedent_server.tool()
async def search_precedent(
    term: str,
    top_k: int = 5,
    min_amount: float | None = None,
    max_amount: float | None = None,
) -> str:
    """Retrieve real U.S. federal procurement award precedents matching a term.

    Args:
        term: Free-text search term describing the good/service (e.g.
            'cloud hosting infrastructure', 'custom software development').
        top_k: Maximum number of ranked award records to return.
        min_amount: Only return awards at or above this obligated amount (USD).
        max_amount: Only return awards at or below this obligated amount (USD).

    Returns:
        JSON string of ranked real award records with vendor, agency, amount,
        description, and a USAspending verification URL.
    """
    index = _state.get_index()
    results = index.search(
        query=term,
        top_k=top_k,
        min_amount=min_amount,
        max_amount=max_amount,
    )
    return json.dumps(index.to_mcp_format(results), indent=2)


if __name__ == "__main__":
    precedent_server.run()
