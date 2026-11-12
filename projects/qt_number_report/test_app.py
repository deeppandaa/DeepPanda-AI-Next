import unittest
import subprocess
import json
import tempfile
import os

class TestApp(unittest.TestCase):

    def run_app(self, input_content=None, input_file_name='input.json'):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, input_file_name)
            if input_content is not None:
                with open(filepath, 'w') as f:
                    f.write(input_content)
            result = subprocess.run(
                ['python', 'app.py', filepath],
                capture_output=True,
                text=True
            )
            return result

    def test_valid_empty_array(self):
        res = self.run_app('[]')
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data, {"count": 0, "total": 0, "minimum": None, "maximum": None})

    def test_valid_single_integer(self):
        res = self.run_app('[42]')
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data, {"count": 1, "total": 42, "minimum": 42, "maximum": 42})

    def test_valid_multiple_integers(self):
        res = self.run_app('[1, -5, 10]')
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["total"], 6)
        self.assertEqual(data["minimum"], -5)
        self.assertEqual(data["maximum"], 10)

    def test_valid_duplicates(self):
        res = self.run_app('[2, 2, 2]')
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["total"], 6)

    def test_invalid_non_array_root(self):
        res = self.run_app('42')
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), '')

    def test_invalid_boolean_in_array(self):
        res = self.run_app('[1, true]')
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), '')

    def test_invalid_float_in_array(self):
        res = self.run_app('[1.5]')
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), '')

    def test_missing_file(self):
        res = self.run_app(input_file_name='nonexistent.json')
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), '')

if __name__ == '__main__':
    unittest.main()
