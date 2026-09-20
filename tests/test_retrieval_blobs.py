"""Tests for the embedding-blob encoding."""

from __future__ import annotations

import numpy as np

from corpus_query.retrieval.blobs import blob_to_vector, vector_to_blob


def test_round_trip_recovers_the_original_values():
    vector = np.array([0.1, -0.2, 3.5, 0.0], dtype=np.float32)

    blob = vector_to_blob(vector)
    recovered = blob_to_vector(blob)

    assert np.allclose(recovered, vector)


def test_round_trip_accepts_a_plain_list():
    vector = [0.25, -0.5, 1.0]

    blob = vector_to_blob(vector)
    recovered = blob_to_vector(blob)

    assert np.allclose(recovered, vector)


def test_blob_is_four_bytes_per_dimension():
    vector = np.zeros(384, dtype=np.float32)

    blob = vector_to_blob(vector)

    assert len(blob) == 384 * 4
