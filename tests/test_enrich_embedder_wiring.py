"""Tests that enrichment reaches for the passage side of the embedder.

bge is asymmetric: a query carries an instruction prefix and a passage does
not. Chunks are passages. Embedding them through the query function would
still produce vectors and still store them, and retrieval would just be
quietly worse — which is why this is asserted rather than assumed.
"""

from __future__ import annotations

import pytest

#: Importing the embedder imports sentence-transformers, and with it torch.
#: Skip the file when the models extra is not installed, which is how CI runs
#: it — the import below would otherwise fail at collection, before the slow
#: mark could deselect anything.
pytest.importorskip("sentence_transformers")

#: Marked at module scope: the assertions are cheap, but importing torch to
#: make them is not.
pytestmark = pytest.mark.slow

from corpus_query.enrich.embed import _project_embedder  # noqa: E402
from corpus_query.models.embedder import (  # noqa: E402
    EMBEDDING_MODEL_ID,
    embed_documents,
    embed_queries,
)
from scripts.enrich import build_embedder  # noqa: E402


def test_the_library_default_embeds_chunks_as_passages():
    embed, model_id = _project_embedder()

    assert embed is embed_documents
    assert embed is not embed_queries
    assert model_id == EMBEDDING_MODEL_ID


def test_the_script_loads_the_same_embedder_the_library_would():
    assert build_embedder() == _project_embedder()
