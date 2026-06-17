import contextlib
import unittest

from roca_cloud.layers import normalize_layer, sync_layers_table
from roca_cloud.store import roca_store


class FakeDb:
    def __init__(self, query_rows=None):
        self.query_rows = query_rows or []
        self.queries = []
        self.executes = []
        self.inserts = []

    def query(self, sql, params=None):
        self.queries.append((sql, params or []))
        return self.query_rows

    def execute(self, sql, params=None):
        self.executes.append((sql, params or []))

    def insert_returning_id(self, sql, params=None):
        self.inserts.append((sql, params or []))
        return 123

    @contextlib.contextmanager
    def transaction(self):
        yield


class StoreContractTest(unittest.TestCase):
    def test_aliases_are_normalized_before_write(self):
        db = FakeDb()
        result = roca_store(
            db,
            layer="handover",
            content="example hello world",
            origin="agent",
            source_agent="example-agent",
            project="aws",
        )

        self.assertEqual(result, {"id": 123, "skipped": False})
        insert_sql, insert_params = db.inserts[0]
        self.assertIn("?::jsonb", insert_sql)
        self.assertEqual(insert_params[0], "handoff")
        self.assertEqual(insert_params[1], "example hello world")
        self.assertEqual(insert_params[3], "agent")

    def test_byte_identical_active_memory_is_deduped_by_project(self):
        db = FakeDb(query_rows=[{"id": 77}])
        result = roca_store(
            db,
            layer="project",
            content="same",
            origin="agent",
            project="aws",
        )

        self.assertEqual(result, {"id": 77, "skipped": True})
        self.assertEqual(db.inserts, [])
        self.assertIn("IS NOT DISTINCT FROM", db.queries[0][0])

    def test_unknown_layer_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "valid ingest layer"):
            normalize_layer("task")

    def test_sync_layers_writes_registry_rows(self):
        db = FakeDb()
        count = sync_layers_table(db)
        self.assertEqual(count, 12)
        self.assertEqual(len(db.executes), 13)
        self.assertIn("ON CONFLICT", db.executes[0][0])


if __name__ == "__main__":
    unittest.main()
