import unittest
from app import add
class Tests(unittest.TestCase):
    def test_add(self): self.assertEqual(add(20,22),42)
    def test_negative(self): self.assertEqual(add(-1,1),0)
