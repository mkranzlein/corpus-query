"""Loading and calling the embedding and reranking models.

Both models load once, through :func:`corpus_query.models.embedder.load_embedder`
and :func:`corpus_query.models.reranker.load_reranker`, and are reused for
every call after that. Weights are cached inside the project rather than in
a user's home directory; see :mod:`corpus_query.models.hf_home`.
"""
