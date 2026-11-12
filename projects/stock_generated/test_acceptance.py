import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from inventory import Inventory


class IndependentAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "independent.db")

    def cli(self, *args, ok=True, database=None):
        result = subprocess.run(
            [sys.executable, "-B", str(Path(__file__).with_name("app.py")),
             "--db", database or self.db, *args],
            capture_output=True, text=True, encoding="utf-8", timeout=10,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
        )
        if not ok:
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "")
            return None
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        data = json.loads(result.stdout)
        self.assertEqual(set(data), {"name", "quantity"})
        return data

    def test_api_accumulates_many_quantities_and_reopens(self):
        expected = {}
        inv = Inventory(self.db)
        try:
            for index in range(75):
                name = "product-" + str(index % 7)
                amount = (index * 13) % 23
                inv.add(name, amount)
                expected[name] = expected.get(name, 0) + amount
            for name, quantity in expected.items():
                self.assertEqual(inv.search(name), quantity)
        finally:
            inv.close()
        inv = Inventory(self.db)
        try:
            for name, quantity in expected.items():
                self.assertEqual(inv.search(name), quantity)
        finally:
            inv.close()

    def test_api_negative_is_rejected_without_mutation(self):
        inv = Inventory(self.db)
        try:
            inv.add("known", 19)
            for name in ("known", "new"):
                with self.assertRaises(ValueError):
                    inv.add(name, -3)
            self.assertEqual(inv.search("known"), 19)
            self.assertIsNone(inv.search("new"))
        finally:
            inv.close()

    def test_cli_accumulation_zero_and_persistence(self):
        for amount, total in ((17, 17), (8, 25), (0, 25), (29, 54)):
            self.assertEqual(self.cli("add", "apple", str(amount)), {"name": "apple", "quantity": total})
        self.assertEqual(self.cli("get", "apple"), {"name": "apple", "quantity": 54})

    def test_cli_negative_does_not_mutate_existing_or_create_missing(self):
        self.cli("add", "known", "11")
        for name in ("known", "missing"):
            self.cli("add", name, "-1", ok=False)
        self.assertEqual(self.cli("get", "known")["quantity"], 11)
        self.assertIsNone(self.cli("get", "missing")["quantity"])

    def test_cli_sql_special_and_unicode_names_remain_distinct(self):
        names = ["x'; DROP TABLE items; --", 'a"b', "line\nbreak", "\u00e7ay", "ordinary"]
        for index, name in enumerate(names):
            self.assertEqual(self.cli("add", name, str(index + 1)), {"name": name, "quantity": index + 1})
        for index, name in enumerate(names):
            self.assertEqual(self.cli("get", name), {"name": name, "quantity": index + 1})

    def test_cli_missing_and_zero_new_product(self):
        self.assertEqual(self.cli("get", "absent"), {"name": "absent", "quantity": None})
        self.assertEqual(self.cli("add", "zero", "0"), {"name": "zero", "quantity": 0})

    def test_cli_invalid_integer_rejected(self):
        for invalid in ("1.5", "not-a-number"):
            self.cli("add", "invalid", invalid, ok=False)
        self.assertIsNone(self.cli("get", "invalid")["quantity"])

    def test_cli_database_isolation(self):
        self.cli("add", "isolated", "31")
        other = str(Path(self.tmp.name) / "other.db")
        self.assertIsNone(self.cli("get", "isolated", database=other)["quantity"])
        self.assertEqual(self.cli("get", "isolated")["quantity"], 31)
