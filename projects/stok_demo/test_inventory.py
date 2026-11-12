import unittest
from tempfile import NamedTemporaryFile
from inventory import Inventory

class TestInventory(unittest.TestCase):
    def test_add(self):
        with NamedTemporaryFile(delete=False) as temp_file:
            db_path = temp_file.name
            inv = Inventory(db_path)
            inv.add('apple', 10)
            inv.add('apple', 5)
            self.assertEqual(inv.search('apple'), 15)

    def test_negative_quantity(self):
        with NamedTemporaryFile(delete=False) as temp_file:
            db_path = temp_file.name
            inv = Inventory(db_path)
            with self.assertRaises(ValueError):
                inv.add('apple', -1)

    def test_reopen(self):
        with NamedTemporaryFile(delete=False) as temp_file:
            db_path = temp_file.name
            inv = Inventory(db_path)
            inv.add('apple', 10)
            inv.close()
            inv = Inventory(db_path)
            self.assertEqual(inv.search('apple'), 10)

    def test_search(self):
        with NamedTemporaryFile(delete=False) as temp_file:
            db_path = temp_file.name
            inv = Inventory(db_path)
            inv.add('apple', 10)
            self.assertEqual(inv.search('apple'), 10)
            self.assertIsNone(inv.search('banana'))

if __name__ == '__main__':
    unittest.main()