"""
test_producer.py — unit tests for producer.py's pure functions.

generate_event_id specifically documents an intended dedup property: the same
(user_id, ad_id, session_id) within the same minute should produce the same
event_id, so Kafka's at-least-once delivery plus a downstream upsert can
absorb a duplicate send without double-counting. Chapter 4 of the tutorial
flags that this property currently can never trigger in practice, because
session_id is a fresh uuid4() on every single event in main() — this test
suite locks in the function's own contract (it DOES work correctly when given
the same session_id) so that gap stays visible and testable, rather than
silently drifting further from the documented intent.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from producer import generate_event_id, get_partition_key  # noqa: E402


class TestGenerateEventId(unittest.TestCase):

    def test_same_inputs_same_minute_produce_same_id(self):
        # This is the property the dedup design depends on. clock is pinned
        # in seconds so both calls land in the same 60s bucket.
        a = generate_event_id("user_1", "ad_1", "session_1", clock=1000.0)
        b = generate_event_id("user_1", "ad_1", "session_1", clock=1000.5)
        self.assertEqual(a, b)

    def test_different_session_produces_different_id(self):
        # This is exactly the gap the tutorial documents: main() generates a
        # fresh session_id per event, so in practice this branch — not the
        # one above — is what actually happens on every call.
        a = generate_event_id("user_1", "ad_1", "session_A", clock=1000.0)
        b = generate_event_id("user_1", "ad_1", "session_B", clock=1000.0)
        self.assertNotEqual(a, b)

    def test_crossing_a_minute_boundary_produces_different_id(self):
        a = generate_event_id("user_1", "ad_1", "session_1", clock=1079.9)
        b = generate_event_id("user_1", "ad_1", "session_1", clock=1080.1)
        self.assertNotEqual(a, b)

    def test_different_user_produces_different_id(self):
        a = generate_event_id("user_1", "ad_1", "session_1", clock=1000.0)
        b = generate_event_id("user_2", "ad_1", "session_1", clock=1000.0)
        self.assertNotEqual(a, b)

    def test_different_ad_produces_different_id(self):
        a = generate_event_id("user_1", "ad_1", "session_1", clock=1000.0)
        b = generate_event_id("user_1", "ad_2", "session_1", clock=1000.0)
        self.assertNotEqual(a, b)

    def test_id_is_a_sha256_hex_digest(self):
        eid = generate_event_id("user_1", "ad_1", "session_1", clock=1000.0)
        self.assertEqual(len(eid), 64)
        int(eid, 16)  # raises ValueError if not valid hex


class TestGetPartitionKey(unittest.TestCase):

    def test_no_salting_returns_bare_ad_id(self):
        event = {"ad_id": "ad_123"}
        self.assertEqual(get_partition_key(event, n_buckets=1), "ad_123")

    def test_salting_appends_a_bucket_suffix(self):
        event = {"ad_id": "ad_hot"}
        key = get_partition_key(event, n_buckets=4)
        self.assertTrue(key.startswith("ad_hot_"))
        suffix = key.rsplit("_", 1)[1]
        self.assertIn(int(suffix), range(4))

    def test_salting_spreads_across_multiple_buckets(self):
        # Not deterministic by design (the salt is random per call) — this
        # asserts the spread property statistically rather than pinning an
        # exact sequence, which would make the test as flaky as the code
        # it's testing if written naively.
        event = {"ad_id": "ad_hot"}
        seen = {get_partition_key(event, n_buckets=4) for _ in range(200)}
        self.assertGreater(len(seen), 1, "200 calls with 4 buckets should not all land in the same bucket")


if __name__ == '__main__':
    unittest.main()
