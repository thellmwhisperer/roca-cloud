import unittest

from roca_cloud.db.postgres import translate_params


class TranslateParamsTest(unittest.TestCase):
    def test_qmark_params_become_psycopg_params(self):
        sql, params = translate_params(
            "SELECT * FROM memories WHERE layer = ? AND origin = ?",
            ["handoff", "agent"],
        )
        self.assertEqual(sql, "SELECT * FROM memories WHERE layer = %s AND origin = %s")
        self.assertEqual(params, ["handoff", "agent"])

    def test_numbered_params_preserve_order_and_reuse(self):
        sql, params = translate_params(
            "SELECT * FROM memories WHERE origin = $2 AND layer = $1 OR project = $2",
            ["handoff", "aws"],
        )
        self.assertEqual(
            sql,
            "SELECT * FROM memories WHERE origin = %s AND layer = %s OR project = %s",
        )
        self.assertEqual(params, ["aws", "handoff", "aws"])

    def test_placeholders_inside_strings_are_ignored(self):
        sql, params = translate_params(
            "SELECT '{\"q\":\"?\", \"d\":\"$1\"}'::jsonb AS payload WHERE layer = ?",
            ["project"],
        )
        self.assertEqual(
            sql,
            "SELECT '{\"q\":\"?\", \"d\":\"$1\"}'::jsonb AS payload WHERE layer = %s",
        )
        self.assertEqual(params, ["project"])


if __name__ == "__main__":
    unittest.main()
