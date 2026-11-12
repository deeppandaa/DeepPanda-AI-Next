import unittest
import json
import os
import subprocess
import tempfile

class TestApp(unittest.TestCase):

    def run_app(self, input_data):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            if isinstance(input_data, list):
                json.dump(input_data, f)
            else:
                f.write(str(input_data))
            temp_path = f.name
        try:
            result = subprocess.run(
                ['python', 'app.py', temp_path],
                capture_output=True,
                text=True
            )
            return result
        finally:
            os.unlink(temp_path)

    def test_valid_input(self):
        data = ["01:30", "02:45"]
        res = self.run_app(data)
        self.assertEqual(res.returncode, 0)
        output = json.loads(res.stdout)
        self.assertEqual(output['count'], 2)
        self.assertEqual(output['total_minutes'], 150)
        self.assertEqual(output['longest_minutes'], 165)

    def test_empty_input(self):
        data = []
        res = self.run_app(data)
        self.assertEqual(res.returncode, 0)
        output = json.loads(res.stdout)
        self.assertEqual(output['count'], 0)
        self.assertEqual(output['total_minutes'], 0)
        self.assertEqual(output['longest_minutes'], 0)

    def test_invalid_format_no_colon(self):
        data = ["130"]
        res = self.run_app(data)
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "")

    def test_invalid_minutes(self):
        data = ["01:60"]
        res = self.run_app(data)
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "")

    def test_non_string_input(self):
        data = [123]
        res = self.run_app(data)
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "")

    def test_unicode_digits(self):
        data = ["０１:３０"] # Unicode digits
        res = self.run_app(data)
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "")

    def test_missing_leading_zero(self):
        data = ["1:30"]
        res = self.run_app(data)
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "")

    def test_non_array_root(self):
        data = {"time": "01:30"}
        res = self.run_app(data)
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "")

if __name__ == '__main__':
    unittest.main()