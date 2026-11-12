import unittest
import tempfile
import os
import json
import subprocess
import sys

class TestInventoryCLI(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, 'test.db')

    def tearDown(self):
        self.tmpdir.cleanup()

    def _run_cli(self, *args):
        cmd = [sys.executable, 'app.py', '--db', self.db_path] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result

    def test_add_and_get(self):
        r1 = self._run_cli('add', 'apple', '10')
        self.assertEqual(r1.returncode, 0)
        data = json.loads(r1.stdout)
        self.assertEqual(data['quantity'], 10)

        r2 = self._run_cli('add', 'apple', '5')
        self.assertEqual(r2.returncode, 0)
        data = json.loads(r2.stdout)
        self.assertEqual(data['quantity'], 15)

    def test_negative_quantity(self):
        r = self._run_cli('add', 'banana', '-1')
        self.assertNotEqual(r.returncode, 0)

    def test_zero_quantity(self):
        r = self._run_cli('add', 'cherry', '0')
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual(data['quantity'], 0)

    def test_missing_product(self):
        r = self._run_cli('get', 'missing')
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertIsNone(data['quantity'])

    def test_quoted_names(self):
        name = "'special'"
        r = self._run_cli('add', name, '1')
        self.assertEqual(r.returncode, 0)
        r2 = self._run_cli('get', name)
        data = json.loads(r2.stdout)
        self.assertEqual(data['quantity'], 1)

    def test_persistence(self):
        self._run_cli('add', 'pear', '5')
        # Simulate reopening by running another command
        r = self._run_cli('get', 'pear')
        data = json.loads(r.stdout)
        self.assertEqual(data['quantity'], 5)

if __name__ == '__main__':
    unittest.main()