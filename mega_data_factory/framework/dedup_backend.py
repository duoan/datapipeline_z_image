"""
Deduplication Backend: Abstract base and implementations

Provides:
- DedupBackend: Abstract base class for deduplication backends
- ExactDedupBackend: Exact key matching (set-based)
- SemanticDedupBackend: Semantic similarity deduplication (vector-based, e.g., FAISS)
"""

from abc import ABC, abstractmethod
from collections.abc import Callable

import faiss  # type: ignore
import numpy as np
import ray
import ray.exceptions


@ray.remote
class _ExactDedupBucketActor:
    """Ray Actor for a single exact deduplication bucket.

    Each actor maintains only one bucket's seen set.
    This distributes memory across multiple actors.
    """

    def __init__(self, bucket_id: int, track_representative: bool = False):
        self.bucket_id = bucket_id
        self.seen: set = set()
        self.track_representative = track_representative
        # Map from dedup_key to representative sample identifier (e.g., record id)
        self.representative: dict[str, str] = {} if track_representative else {}

    def is_seen(self, key: str) -> bool:
        return key in self.seen

    def mark_seen(self, key: str, representative_id: str | None = None) -> bool:
        if key in self.seen:
            return False
        self.seen.add(key)
        if self.track_representative and representative_id is not None:
            self.representative[key] = representative_id
        return True

    def batch_mark_seen(self, keys: list[str]) -> list[bool]:
        results = []
        for key in keys:
            if key in self.seen:
                results.append(False)
            else:
                self.seen.add(key)
                results.append(True)
        return results

    def batch_mark_seen_with_ids(self, keys: list[str], representative_ids: list[str]) -> list[tuple[bool, str | None]]:
        """Mark keys as seen and return (is_new, representative_id) for each.

        For new keys, representative_id is None.
        For duplicate keys, representative_id is the ID of the first seen sample.
        """
        results = []
        for key, rep_id in zip(keys, representative_ids, strict=False):
            if key in self.seen:
                # Duplicate - return the representative ID
                rep = self.representative.get(key) if self.track_representative else None
                results.append((False, rep))
            else:
                self.seen.add(key)
                if self.track_representative:
                    self.representative[key] = rep_id
                results.append((True, None))
        return results

    def get_representative(self, key: str) -> str | None:
        """Get the representative sample ID for a given key."""
        return self.representative.get(key)

    def reset(self):
        self.seen.clear()
        self.representative.clear()


@ray.remote
class _SemanticDedupBucketActor:
    """Ray Actor for a single semantic deduplication bucket.

    Each actor maintains a vector store (FAISS index) for similarity search.
    Stores embeddings and performs approximate nearest neighbor search to find duplicates.
    """

    def __init__(
        self,
        bucket_id: int,
        embedding_dim: int = 768,
        similarity_threshold: float = 0.95,
        track_representative: bool = False,
        use_faiss: bool = True,
    ):
        """Initialize semantic deduplication bucket actor.

        Args:
            bucket_id: Bucket identifier
            embedding_dim: Dimension of embedding vectors
            similarity_threshold: Similarity threshold (0-1, cosine similarity)
            track_representative: If True, track representative sample IDs
            use_faiss: If True, use FAISS for vector search (requires faiss-cpu/faiss-gpu)
        """
        self.bucket_id = bucket_id
        self.embedding_dim = embedding_dim
        self.similarity_threshold = similarity_threshold
        self.track_representative = track_representative

        # Vector storage
        self.embeddings: list[np.ndarray] = []  # List of stored embeddings
        self.embedding_to_key: dict[int, str] = {}  # Index -> dedup_key
        self.key_to_index: dict[str, int] = {}  # dedup_key -> index in embeddings list
        self.representative: dict[str, str] = {} if track_representative else {}

        # FAISS index (if available)
        self.faiss_index = None
        # Use InnerProduct (cosine similarity when vectors are normalized)
        # For cosine similarity: normalize vectors and use InnerProduct
        self.faiss_index = faiss.IndexFlatIP(embedding_dim)  # Inner Product (for normalized vectors = cosine)

    def _normalize_vector(self, vec: np.ndarray) -> np.ndarray:
        """Normalize vector to unit length for cosine similarity."""
        norm = np.linalg.norm(vec)
        if norm == 0:
            return vec
        return vec / norm

    def _find_similar_embedding(self, embedding: np.ndarray) -> tuple[int | None, float]:
        """Find most similar embedding in the store.

        Returns:
            Tuple of (index, similarity_score) or (None, 0.0) if no similar embedding found
        """
        if not self.embeddings:
            return None, 0.0

        embedding_norm = self._normalize_vector(embedding)

        # Use FAISS for fast similarity search
        # FAISS expects 2D array
        query = embedding_norm.reshape(1, -1).astype(np.float32)
        # Search for top 1 nearest neighbor
        distances, indices = self.faiss_index.search(query, 1)
        if len(indices[0]) > 0 and indices[0][0] >= 0:
            idx = int(indices[0][0])
            similarity = float(distances[0][0])  # Inner product (cosine for normalized vectors)
            if similarity >= self.similarity_threshold:
                return idx, similarity

        return None, 0.0

    def batch_mark_seen(self, embeddings: list[np.ndarray], keys: list[str]) -> list[bool]:
        """Batch check embeddings and mark as seen if not similar to existing ones.

        Args:
            embeddings: List of embedding vectors (numpy arrays)
            keys: List of deduplication keys corresponding to embeddings

        Returns:
            List of booleans: True if embedding is new (not similar to any existing),
            False if duplicate (similar embedding exists)
        """
        results = []
        for embedding, key in zip(embeddings, keys, strict=False):
            # Check if key already exists (exact match)
            if key in self.key_to_index:
                results.append(False)
                continue

            # Find similar embedding
            similar_idx, _ = self._find_similar_embedding(embedding)
            if similar_idx is not None:
                # Duplicate found
                results.append(False)
            else:
                # New embedding - add to store
                idx = len(self.embeddings)
                embedding_norm = self._normalize_vector(embedding)
                self.embeddings.append(embedding_norm)
                self.embedding_to_key[idx] = key
                self.key_to_index[key] = idx

                # Add to FAISS index if available
                if self.use_faiss and self.faiss_index is not None:
                    self.faiss_index.add(embedding_norm.reshape(1, -1).astype(np.float32))

                results.append(True)

        return results

    def batch_mark_seen_with_ids(
        self,
        embeddings: list[np.ndarray],
        keys: list[str],
        representative_ids: list[str],
    ) -> list[tuple[bool, str | None]]:
        """Batch check embeddings and return (is_new, representative_id) for each.

        Args:
            embeddings: List of embedding vectors
            keys: List of deduplication keys
            representative_ids: List of sample identifiers

        Returns:
            List of (is_new, representative_id) tuples. For new keys, representative_id is None.
            For duplicate keys, representative_id is the ID of the first seen sample.
        """
        results = []
        for embedding, key, rep_id in zip(embeddings, keys, representative_ids, strict=False):
            # Check if key already exists (exact match)
            if key in self.key_to_index:
                existing_idx = self.key_to_index[key]
                existing_key = self.embedding_to_key[existing_idx]
                rep = self.representative.get(existing_key) if self.track_representative else None
                results.append((False, rep))
                continue

            # Find similar embedding
            similar_idx, similarity = self._find_similar_embedding(embedding)
            if similar_idx is not None:
                # Duplicate found - return representative ID
                similar_key = self.embedding_to_key[similar_idx]
                rep = self.representative.get(similar_key) if self.track_representative else None
                results.append((False, rep))
            else:
                # New embedding - add to store
                idx = len(self.embeddings)
                embedding_norm = self._normalize_vector(embedding)
                self.embeddings.append(embedding_norm)
                self.embedding_to_key[idx] = key
                self.key_to_index[key] = idx

                # Track representative if enabled
                if self.track_representative:
                    self.representative[key] = rep_id

                # Add to FAISS index if available
                if self.use_faiss and self.faiss_index is not None:
                    self.faiss_index.add(embedding_norm.reshape(1, -1).astype(np.float32))

                results.append((True, None))

        return results

    def reset(self):
        """Reset all vector store states."""
        self.embeddings.clear()
        self.embedding_to_key.clear()
        self.key_to_index.clear()
        self.representative.clear()
        if self.faiss_index is not None:
            self.faiss_index.reset()


class DedupBackend(ABC):
    """Abstract base class for deduplication backends.

    Subclasses implement different deduplication strategies:
    - ExactDedupBackend: Exact key matching (set-based)
    - SemanticDedupBackend: Semantic similarity (vector-based, e.g., FAISS)
    """

    @property
    @abstractmethod
    def track_representative(self) -> bool:
        """Whether this backend tracks representative sample IDs."""
        pass

    @abstractmethod
    def batch_mark_seen(self, keys: list[str]) -> list[bool]:
        """Batch check and mark keys as seen.

        Args:
            keys: List of deduplication keys

        Returns:
            List of booleans: True if key is new (not seen before), False if duplicate
        """
        pass

    @abstractmethod
    def batch_mark_seen_with_ids(self, keys: list[str], representative_ids: list[str]) -> list[tuple[bool, str | None]]:
        """Batch mark keys as seen and return (is_new, representative_id) for each.

        Args:
            keys: List of deduplication keys
            representative_ids: List of sample identifiers (e.g., record IDs)

        Returns:
            List of (is_new, representative_id) tuples. For new keys, representative_id is None.
            For duplicate keys, representative_id is the ID of the first seen sample.
        """
        pass

    @abstractmethod
    def reset(self):
        """Reset all deduplication state."""
        pass


class ExactDedupBackend(DedupBackend):
    """Exact key matching deduplication backend with bucketing.

    Uses exact key matching (set-based) - two records are duplicates if their
    dedup keys are identical.

    Each bucket is maintained by a separate Ray Actor. Keys are routed to
    specific bucket actors, distributing memory across actors.

    Performance guidelines:
    - For small datasets (<1B keys): 16-64 buckets is sufficient
    - For medium datasets (1B-10B keys): 256-1000 buckets recommended
    - For large datasets (10B-100B keys): 1000-10000 buckets recommended
    - Target: Keep ~10M-100M keys per bucket for optimal performance

    Note: For cluster-based deduplication (pre-clustered records), you can use
    cluster_id as bucket_id via custom bucket_id_getter. This still uses exact
    matching within each cluster bucket, not semantic similarity.
    """

    def __init__(
        self,
        num_buckets: int = 2,
        name_prefix: str = "exact_dedup_actor",
        bucket_id_getter: Callable[[str], int] | None = None,
        track_representative: bool = False,
    ):
        """Initialize exact deduplication backend with bucketing.

        Args:
            num_buckets: Number of bucket actors to create (default: 16)
                        Increase for large datasets to distribute memory load.
                        See class docstring for performance guidelines.
            name_prefix: Prefix for Ray Actor names (for Ray Dashboard visibility)
            bucket_id_getter: Optional function(key: str) -> int to compute bucket_id.
                             If None, uses hash(key) % num_buckets.
            track_representative: If True, track the representative sample ID for each key.
                                 This enables returning the representative ID when duplicates are found.
        """
        self._track_representative = track_representative
        self.num_buckets = num_buckets
        self.bucket_id_getter = bucket_id_getter
        self.name_prefix = name_prefix

        # Create one actor per bucket (or reuse existing ones)
        self.bucket_actors = []
        for bucket_id in range(num_buckets):
            actor_name = f"{name_prefix}_bucket_{bucket_id}"
            try:
                actor = ray.get_actor(actor_name)
            except ValueError:
                try:
                    actor = _ExactDedupBucketActor.options(name=actor_name).remote(
                        bucket_id, track_representative=track_representative
                    )
                except ray.exceptions.ActorAlreadyExistsError:
                    actor = ray.get_actor(actor_name)
            self.bucket_actors.append(actor)

    @property
    def track_representative(self) -> bool:
        return self._track_representative

    def _get_bucket_id(self, key: str) -> int:
        """Get bucket ID for a given key."""
        if self.bucket_id_getter:
            return self.bucket_id_getter(key) % self.num_buckets
        return hash(key) % self.num_buckets

    def _get_actor(self, key: str):
        """Get the bucket actor for a given key."""
        bucket_id = self._get_bucket_id(key)
        return self.bucket_actors[bucket_id]

    def batch_mark_seen(self, keys: list[str]) -> list[bool]:
        """Batch mark multiple keys as seen (grouped by bucket for efficiency)."""
        # Group keys by bucket
        bucket_keys: dict[int, list[tuple]] = {}  # bucket_id -> [(original_index, key), ...]
        for idx, key in enumerate(keys):
            bucket_id = self._get_bucket_id(key)
            if bucket_id not in bucket_keys:
                bucket_keys[bucket_id] = []
            bucket_keys[bucket_id].append((idx, key))

        # Process each bucket in parallel
        futures = {}
        for bucket_id, key_list in bucket_keys.items():
            actor = self.bucket_actors[bucket_id]
            bucket_keys_only = [k for _, k in key_list]
            futures[bucket_id] = (actor.batch_mark_seen.remote(bucket_keys_only), key_list)

        # Collect results and reconstruct original order
        results = [False] * len(keys)
        for future, key_list in futures.values():
            bucket_results = ray.get(future)
            for (orig_idx, _), result in zip(key_list, bucket_results, strict=False):
                results[orig_idx] = result

        return results

    def batch_mark_seen_with_ids(self, keys: list[str], representative_ids: list[str]) -> list[tuple[bool, str | None]]:
        """Batch mark keys as seen and return (is_new, representative_id) for each.

        For new keys, representative_id is None.
        For duplicate keys, representative_id is the ID of the first seen sample.

        Args:
            keys: List of deduplication keys
            representative_ids: List of sample identifiers (e.g., record IDs)

        Returns:
            List of (is_new, representative_id) tuples
        """
        # Group keys by bucket
        bucket_data: dict[int, list[tuple[int, str, str]]] = {}  # bucket_id -> [(orig_idx, key, rep_id), ...]
        for idx, (key, rep_id) in enumerate(zip(keys, representative_ids, strict=False)):
            bucket_id = self._get_bucket_id(key)
            if bucket_id not in bucket_data:
                bucket_data[bucket_id] = []
            bucket_data[bucket_id].append((idx, key, rep_id))

        # Process each bucket in parallel
        futures = {}
        for bucket_id, data_list in bucket_data.items():
            actor = self.bucket_actors[bucket_id]
            bucket_keys = [k for _, k, _ in data_list]
            bucket_rep_ids = [r for _, _, r in data_list]
            futures[bucket_id] = (
                actor.batch_mark_seen_with_ids.remote(bucket_keys, bucket_rep_ids),
                data_list,
            )

        # Collect results and reconstruct original order
        results: list[tuple[bool, str | None]] = [(False, None)] * len(keys)
        for future, data_list in futures.values():
            bucket_results = ray.get(future)
            for (orig_idx, _, _), result in zip(data_list, bucket_results, strict=False):
                results[orig_idx] = result

        return results

    def reset(self):
        """Reset all bucket states."""
        futures = [actor.reset.remote() for actor in self.bucket_actors]
        ray.get(futures)


class SemanticDedupBackend(DedupBackend):
    """Semantic similarity deduplication backend (vector-based).

    Uses vector similarity search (FAISS) to find semantically similar records.
    Two records are duplicates if their embeddings are similar within a threshold.

    **Note**: This backend expects embeddings (numpy arrays), not string keys.
    For use with Deduplicator, the semantic deduplicator should extract embeddings
    from records and pass them via batch_mark_seen_embeddings().

    Design considerations:
    - Store embeddings in distributed vector store (one FAISS index per bucket actor)
    - Use approximate nearest neighbor search (ANN) for similarity matching
    - Support configurable similarity threshold (cosine similarity)
    - Batch operations for efficiency
    """

    def __init__(
        self,
        num_buckets: int = 2,
        name_prefix: str = "semantic_dedup_actor",
        similarity_threshold: float = 0.95,
        embedding_dim: int = 768,
        track_representative: bool = False,
        use_faiss: bool = True,
        bucket_id_getter: Callable[[str], int] | None = None,
    ):
        """Initialize semantic deduplication backend.

        Args:
            num_buckets: Number of bucket actors to create
            name_prefix: Prefix for Ray Actor names
            similarity_threshold: Similarity threshold (0-1, cosine similarity)
            embedding_dim: Dimension of embedding vectors
            track_representative: If True, track representative sample IDs
            use_faiss: If True, use FAISS for vector search (requires faiss-cpu/faiss-gpu)
            bucket_id_getter: Optional function(key: str) -> int to compute bucket_id.
                             If None, uses hash(key) % num_buckets.
        """
        self._track_representative = track_representative
        self.num_buckets = num_buckets
        self.name_prefix = name_prefix
        self.similarity_threshold = similarity_threshold
        self.embedding_dim = embedding_dim
        self.bucket_id_getter = bucket_id_getter

        # Create one actor per bucket
        self.bucket_actors = []
        for bucket_id in range(num_buckets):
            actor_name = f"{name_prefix}_bucket_{bucket_id}"
            try:
                actor = ray.get_actor(actor_name)
            except ValueError:
                try:
                    actor = _SemanticDedupBucketActor.options(name=actor_name).remote(
                        bucket_id=bucket_id,
                        embedding_dim=embedding_dim,
                        similarity_threshold=similarity_threshold,
                        track_representative=track_representative,
                        use_faiss=use_faiss,
                    )
                except ray.exceptions.ActorAlreadyExistsError:
                    actor = ray.get_actor(actor_name)
            self.bucket_actors.append(actor)

    @property
    def track_representative(self) -> bool:
        return self._track_representative

    def _get_bucket_id(self, key: str) -> int:
        """Get bucket ID for a given key."""
        if self.bucket_id_getter:
            return self.bucket_id_getter(key) % self.num_buckets
        return hash(key) % self.num_buckets

    def batch_mark_seen(self, keys: list[str]) -> list[bool]:
        """Batch check keys (for compatibility with DedupBackend interface).

        **Note**: For semantic deduplication, use batch_mark_seen_embeddings() instead.
        This method raises NotImplementedError as semantic dedup requires embeddings.

        Args:
            keys: List of deduplication keys

        Returns:
            List of booleans
        """
        raise NotImplementedError(
            "SemanticDedupBackend.batch_mark_seen() requires embeddings, not keys. "
            "Use batch_mark_seen_embeddings() instead."
        )

    def batch_mark_seen_embeddings(self, embeddings: list[np.ndarray], keys: list[str]) -> list[bool]:
        """Batch check embeddings against vector store.

        Args:
            embeddings: List of embedding vectors (numpy arrays of shape (embedding_dim,))
            keys: List of deduplication keys corresponding to embeddings

        Returns:
            List of booleans: True if embedding is new (no similar embedding found),
            False if duplicate (similar embedding exists)
        """
        if len(embeddings) != len(keys):
            raise ValueError(f"embeddings and keys must have same length: {len(embeddings)} != {len(keys)}")

        # Group by bucket
        bucket_data: dict[int, list[tuple[int, np.ndarray, str]]] = {}
        for idx, (emb, key) in enumerate(zip(embeddings, keys, strict=False)):
            bucket_id = self._get_bucket_id(key)
            if bucket_id not in bucket_data:
                bucket_data[bucket_id] = []
            bucket_data[bucket_id].append((idx, emb, key))

        # Process each bucket in parallel
        futures = {}
        for bucket_id, data_list in bucket_data.items():
            actor = self.bucket_actors[bucket_id]
            bucket_embeddings = [emb for _, emb, _ in data_list]
            bucket_keys = [key for _, _, key in data_list]
            futures[bucket_id] = (actor.batch_mark_seen.remote(bucket_embeddings, bucket_keys), data_list)

        # Collect results and reconstruct original order
        results = [False] * len(keys)
        for future, data_list in futures.values():
            bucket_results = ray.get(future)
            for (orig_idx, _, _), result in zip(data_list, bucket_results, strict=False):
                results[orig_idx] = result

        return results

    def batch_mark_seen_with_ids(self, keys: list[str], representative_ids: list[str]) -> list[tuple[bool, str | None]]:
        """Batch check keys (for compatibility with DedupBackend interface).

        **Note**: For semantic deduplication, use batch_mark_seen_embeddings_with_ids() instead.
        This method raises NotImplementedError as semantic dedup requires embeddings.

        Args:
            keys: List of deduplication keys
            representative_ids: List of sample identifiers

        Returns:
            List of (is_new, representative_id) tuples
        """
        raise NotImplementedError(
            "SemanticDedupBackend.batch_mark_seen_with_ids() requires embeddings, not keys. "
            "Use batch_mark_seen_embeddings_with_ids() instead."
        )

    def batch_mark_seen_embeddings_with_ids(
        self,
        embeddings: list[np.ndarray],
        keys: list[str],
        representative_ids: list[str],
    ) -> list[tuple[bool, str | None]]:
        """Batch check embeddings and return (is_new, representative_id).

        Args:
            embeddings: List of embedding vectors
            keys: List of deduplication keys
            representative_ids: List of sample identifiers

        Returns:
            List of (is_new, representative_id) tuples
        """
        if len(embeddings) != len(keys) or len(keys) != len(representative_ids):
            raise ValueError(
                f"embeddings, keys, and representative_ids must have same length: "
                f"{len(embeddings)} != {len(keys)} != {len(representative_ids)}"
            )

        # Group by bucket
        bucket_data: dict[int, list[tuple[int, np.ndarray, str, str]]] = {}
        for idx, (emb, key, rep_id) in enumerate(zip(embeddings, keys, representative_ids, strict=False)):
            bucket_id = self._get_bucket_id(key)
            if bucket_id not in bucket_data:
                bucket_data[bucket_id] = []
            bucket_data[bucket_id].append((idx, emb, key, rep_id))

        # Process each bucket in parallel
        futures = {}
        for bucket_id, data_list in bucket_data.items():
            actor = self.bucket_actors[bucket_id]
            bucket_embeddings = [emb for _, emb, _, _ in data_list]
            bucket_keys = [key for _, _, key, _ in data_list]
            bucket_rep_ids = [rep_id for _, _, _, rep_id in data_list]
            futures[bucket_id] = (
                actor.batch_mark_seen_with_ids.remote(bucket_embeddings, bucket_keys, bucket_rep_ids),
                data_list,
            )

        # Collect results and reconstruct original order
        results: list[tuple[bool, str | None]] = [(False, None)] * len(keys)
        for future, data_list in futures.values():
            bucket_results = ray.get(future)
            for (orig_idx, _, _, _), result in zip(data_list, bucket_results, strict=False):
                results[orig_idx] = result

        return results

    def reset(self):
        """Reset all vector store states."""
        futures = [actor.reset.remote() for actor in self.bucket_actors]
        ray.get(futures)
