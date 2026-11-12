import tempfile,unittest
from pathlib import Path
from inventory import Inventory
class Acceptance(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=str(Path(self.tmp.name)/'inventory.db')
        self.inv=Inventory(self.path)
    def tearDown(self):
        self.inv.close()
        self.tmp.cleanup()
    def test_accumulate(self):
        self.inv.add('apple',10)
        self.inv.add('apple',5)
        self.assertEqual(self.inv.search('apple'),15)
    def test_negative_rejected(self):
        with self.assertRaises(ValueError): self.inv.add('apple',-1)
        self.assertIsNone(self.inv.search('apple'))
    def test_absent(self):
        self.assertIsNone(self.inv.search('absent'))
    def test_zero_preserves_existing(self):
        self.inv.add('apple',10)
        self.inv.add('apple',0)
        self.assertEqual(self.inv.search('apple'),10)
    def test_quotes(self):
        self.inv.add("a'; DROP TABLE inventory; --",3)
        self.assertEqual(self.inv.search("a'; DROP TABLE inventory; --"),3)
    def test_persistence(self):
        self.inv.add('apple',8)
        self.inv.close()
        self.inv=Inventory(self.path)
        self.assertEqual(self.inv.search('apple'),8)
