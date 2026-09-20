"""Converting an embedding vector to a SQLite blob and back.

One place does this so the writer (the embedding pipeline that fills
``chunks.embedding``) and the reader (the vector index, built from that
column) cannot drift apart on dtype or byte order.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

#: Vectors are stored as 32-bit floats: half the size of float64, and what
#: the embedding model emits natively, so no precision is spent converting
#: either direction.
DTYPE = np.float32


def vector_to_blob(vector: Sequence[float] | np.ndarray) -> bytes:
    """Encode a vector as the bytes stored in ``chunks.embedding``.

    Args:
        vector: The embedding to encode.

    Returns:
        Its raw bytes, as contiguous little-endian ``DTYPE`` values.
    """
    return np.asarray(vector, dtype=DTYPE).tobytes()


def blob_to_vector(blob: bytes) -> np.ndarray:
    """Decode a ``chunks.embedding`` blob back into a vector.

    Args:
        blob: Bytes as produced by :func:`vector_to_blob`.

    Returns:
        The embedding, as an array of ``DTYPE``.
    """
    return np.frombuffer(blob, dtype=DTYPE)
