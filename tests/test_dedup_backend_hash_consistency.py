#!/usr/bin/env python3
"""
Tests for DedupBackend Hash Consistency

This test file validates that the hash function used for bucket assignment
in DedupBackend is consistent across processes.

The tests demonstrate:
1. Python hash() is NOT consistent across processes (breaks distributed dedup)
2. xxHash IS consistent across processes (required for distributed dedup)

Run with:
    python tests/test_dedup_backend_hash_consistency.py
"""

import multiprocessing as mp
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Ensure 'spawn' start method so each subprocess gets a fresh PYTHONHASHSEED.
# Must be called before any Process is created.
# On Linux the default is 'fork' which inherits the parent's seed,
# causing Python hash() to appear consistent and hiding the bug.
try:
    mp.set_start_method("spawn")
except RuntimeError:
    pass  # Already set (e.g. macOS Python 3.8+)

try:
    import xxhash
    XXHASH_AVAILABLE = True
except ImportError:
    XXHASH_AVAILABLE = False
    print("ERROR: xxhash not installed. Run: pip install xxhash")
    sys.exit(1)


# ============================================================================
# Test Data
# ============================================================================

TEST_KEYS = [
    "https://example.com/images/abc123.jpg",
    "a1b2c3d4e5f67890abcdef1234567890",
    "550e8400-e29b-41d4-a716-446655440000",
    "content_hash_sha256_abc123",
]

NUM_BUCKETS = 256


# ============================================================================
# Worker Functions
# ============================================================================

def python_hash_worker(keys, num_buckets, result_queue, worker_id):
    """Worker that computes Python hash() bucket assignments.

    Returns a list of (key, bucket_id) tuples to preserve duplicate keys.
    """
    results = [(key, hash(key) % num_buckets) for key in keys]
    result_queue.put((worker_id, results))


def xxhash_worker(keys, num_buckets, result_queue, worker_id):
    """Worker that computes xxHash bucket assignments.

    Returns a list of (key, bucket_id) tuples to preserve duplicate keys.
    """
    results = [(key, xxhash.xxh64(key).intdigest() % num_buckets) for key in keys]
    result_queue.put((worker_id, results))


# ============================================================================
# Tests
# (Functions are prefixed with 'run_' rather than 'test_' to prevent pytest
# from collecting them — they require positional args and spawn subprocesses.)
# ============================================================================

def run_python_hash_consistency(num_workers=4):
    """Test that Python hash() is INCONSISTENT across processes.

    Returns True when inconsistency is detected (confirming the known bug).
    """
    print("\n" + "=" * 80)
    print("Test 1: Python hash() Consistency")
    print("=" * 80)

    result_queue = mp.Queue()
    processes = []

    for i in range(num_workers):
        p = mp.Process(target=python_hash_worker, args=(TEST_KEYS, NUM_BUCKETS, result_queue, i))
        processes.append(p)
        p.start()

    for p in processes:
        p.join()

    # Collect results; TEST_KEYS are unique so dict() conversion is safe for lookup
    all_results = {}
    while not result_queue.empty():
        worker_id, results = result_queue.get()
        all_results[worker_id] = dict(results)

    # Check consistency
    inconsistent_count = 0
    for key in TEST_KEYS:
        bucket_ids = set(all_results[wid][key] for wid in range(num_workers))
        if len(bucket_ids) > 1:
            inconsistent_count += 1
            print(f"\n  Key: {key[:50]}...")
            print(f"  Got {len(bucket_ids)} different bucket IDs: {bucket_ids}")

    if inconsistent_count > 0:
        print(f"\n\u274c RESULT: Python hash() is INCONSISTENT across {num_workers} processes!")
        print(f"   {inconsistent_count}/{len(TEST_KEYS)} keys got different bucket IDs")
        return True   # Bug confirmed
    else:
        print(f"\n\u26a0\ufe0f Python hash() was consistent (unexpected — check 'spawn' start method)")
        return False


def run_xxhash_consistency(num_workers=4):
    """Test that xxHash is CONSISTENT across processes.

    Returns True when all keys are consistent (expected correct behaviour).
    """
    print("\n" + "=" * 80)
    print("Test 2: xxHash64 Consistency")
    print("=" * 80)

    result_queue = mp.Queue()
    processes = []

    for i in range(num_workers):
        p = mp.Process(target=xxhash_worker, args=(TEST_KEYS, NUM_BUCKETS, result_queue, i))
        processes.append(p)
        p.start()

    for p in processes:
        p.join()

    # Collect results; TEST_KEYS are unique so dict() conversion is safe for lookup
    all_results = {}
    while not result_queue.empty():
        worker_id, results = result_queue.get()
        all_results[worker_id] = dict(results)

    # Check consistency
    inconsistent_count = 0
    for key in TEST_KEYS:
        bucket_ids = set(all_results[wid][key] for wid in range(num_workers))
        if len(bucket_ids) > 1:
            inconsistent_count += 1
            print(f"\n  Key: {key[:50]}...")
            print(f"  Got {len(bucket_ids)} different bucket IDs: {bucket_ids}")

    if inconsistent_count == 0:
        print(f"\n\u2705 RESULT: xxHash64 is CONSISTENT across {num_workers} processes!")
        print(f"   All keys got the same bucket ID from all processes")
        return True
    else:
        print(f"\n\u274c xxHash was inconsistent (unexpected!)")
        return False


def run_dedup_simulation(num_workers=4):
    """Simulate deduplication with both hash functions."""
    print("\n" + "=" * 80)
    print("Test 3: Deduplication Simulation")
    print("=" * 80)

    # Create records with duplicates (each key appears multiple times)
    all_keys = TEST_KEYS * 4  # 16 keys total, each of the 4 unique keys appears 4 times
    expected_unique = len(TEST_KEYS)
    expected_duplicates = len(all_keys) - expected_unique

    print(f"\n  Total records: {len(all_keys)}")
    print(f"  Expected unique: {expected_unique}")
    print(f"  Expected duplicates: {expected_duplicates}")

    import math
    chunk_size = math.ceil(len(all_keys) / num_workers)

    # ---- Python hash() ----
    print("\n--- Python hash() Deduplication ---")
    result_queue = mp.Queue()
    processes = []

    for i in range(num_workers):
        worker_keys = all_keys[i * chunk_size:(i + 1) * chunk_size]
        p = mp.Process(target=python_hash_worker, args=(worker_keys, NUM_BUCKETS, result_queue, i))
        processes.append(p)
        p.start()

    for p in processes:
        p.join()

    # Iterate tuples (not dict) to count every occurrence, including intra-worker duplicates
    python_seen: set = set()
    python_duplicates = 0
    while not result_queue.empty():
        _worker_id, results = result_queue.get()
        for key, bucket_id in results:  # results is list[tuple]
            pair = (key, bucket_id)
            if pair in python_seen:
                python_duplicates += 1
            else:
                python_seen.add(pair)

    python_detection_rate = python_duplicates / expected_duplicates * 100 if expected_duplicates > 0 else 0
    print(f"  Unique (key, bucket) pairs: {len(python_seen)}")
    print(f"  Duplicates detected: {python_duplicates}")
    print(f"  Detection rate: {python_detection_rate:.1f}%")

    # ---- xxHash64 ----
    print("\n--- xxHash64 Deduplication ---")
    result_queue = mp.Queue()
    processes = []

    for i in range(num_workers):
        worker_keys = all_keys[i * chunk_size:(i + 1) * chunk_size]
        p = mp.Process(target=xxhash_worker, args=(worker_keys, NUM_BUCKETS, result_queue, i))
        processes.append(p)
        p.start()

    for p in processes:
        p.join()

    xxhash_seen: set = set()
    xxhash_duplicates = 0
    while not result_queue.empty():
        _worker_id, results = result_queue.get()
        for key, bucket_id in results:  # results is list[tuple]
            pair = (key, bucket_id)
            if pair in xxhash_seen:
                xxhash_duplicates += 1
            else:
                xxhash_seen.add(pair)

    xxhash_detection_rate = xxhash_duplicates / expected_duplicates * 100 if expected_duplicates > 0 else 0
    print(f"  Unique (key, bucket) pairs: {len(xxhash_seen)}")
    print(f"  Duplicates detected: {xxhash_duplicates}")
    print(f"  Detection rate: {xxhash_detection_rate:.1f}%")


def verify_current_implementation():
    """Verify that current dedup_backend.py uses Python hash()."""
    print("\n" + "=" * 80)
    print("Test 4: Current Implementation Verification")
    print("=" * 80)

    # Read the source file directly
    dedup_backend_path = Path(__file__).parent.parent / "mega_data_factory" / "framework" / "dedup_backend.py"

    if not dedup_backend_path.exists():
        print(f"\n  File not found: {dedup_backend_path}")
        return

    with open(dedup_backend_path) as f:
        content = f.read()

    # Check for Python hash() usage in _get_bucket_id
    if "hash(key)" in content and "_get_bucket_id" in content:
        print("\n  ✗ Current implementation uses Python hash(key) in _get_bucket_id()")
        print("  This is the source of the bug!")

        # Find the exact line
        for i, line in enumerate(content.split('\n'), 1):
            if 'hash(key)' in line and 'num_buckets' in line:
                print(f"\n  Line {i}: {line.strip()}")
    else:
        print("\n  ✓ Implementation may have been fixed (no Python hash() found)")


def generate_summary_report():
    """Generate summary report."""
    print("\n" + "=" * 80)
    print("SUMMARY REPORT")
    print("=" * 80)
    print("""
BUG IDENTIFIED:
  ExactDedupBackend._get_bucket_id() uses Python's built-in hash()
  which is NON-DETERMINISTIC across processes.

EVIDENCE:
  1. Python hash() produces different bucket IDs for same key across processes
  2. Deduplication with Python hash() misses most duplicates
  3. xxHash produces consistent bucket IDs across processes
  4. Deduplication with xxHash correctly detects duplicates

IMPACT:
  - In distributed Ray environments, same key gets different bucket IDs
  - Deduplication FAILS - duplicates are not detected
  - Data quality is compromised

FIX:
  In mega_data_factory/framework/dedup_backend.py, replace:

    def _get_bucket_id(self, key: str) -> int:
        return hash(key) % self.num_buckets

  With:

    import xxhash

    def _get_bucket_id(self, key: str) -> int:
        return xxhash.xxh64(key).intdigest() % self.num_buckets

DEPENDENCY:
  Add to pyproject.toml:
    "xxhash>=3.0.0"
""")


def main():
    print("=" * 80)
    print("DedupBackend Hash Consistency Tests")
    print("=" * 80)
    print("\nThis test demonstrates a critical bug in dedup_backend.py")
    print("Python hash() is non-deterministic across processes, breaking distributed deduplication")

    # Use spawn for true process isolation (set at module level above,
    # but force=True here ensures it sticks even if already set by a test runner)
    try:
        mp.set_start_method("spawn", force=True)
    except RuntimeError:
        pass

    # Run tests
    python_is_inconsistent = run_python_hash_consistency(num_workers=4)
    xxhash_is_consistent = run_xxhash_consistency(num_workers=4)
    run_dedup_simulation(num_workers=4)
    verify_current_implementation()

    # Generate report
    generate_summary_report()

    # Final verdict
    print("\n" + "=" * 80)
    print("FINAL VERDICT")
    print("=" * 80)
    if python_is_inconsistent and xxhash_is_consistent:
        print("✓ Bug confirmed: Python hash() is inconsistent, xxHash is consistent")
        print("✓ Recommendation: Replace hash(key) with xxhash.xxh64(key).intdigest()")
    else:
        print("Results may vary - try running with more workers")


if __name__ == "__main__":
    main()
