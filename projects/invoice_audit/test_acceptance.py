import unittest
import subprocess
import sys
import json
import tempfile
import os
from pathlib import Path

class TestAcceptance(unittest.TestCase):

    def run_csv(self, csv_content: str):
        """Helper to run app.py with given CSV content and return (stdout, stderr, returncode)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "input.csv"
            csv_path.write_text(csv_content, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, '-B', str(Path(__file__).with_name('app.py')), str(csv_path)],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout, result.stderr, result.returncode

    def test_trimmed_identical_duplicate_success(self):
        """Case: trimmed identical duplicate should succeed with specific JSON output."""
        csv_content = "invoice_id,customer,amount,status\n 1 , A , 1.00 , paid \n1,A,1.00,paid\n"
        expected = {
            "unique_invoices": 1,
            "duplicates_ignored": 1,
            "total": "1.00",
            "customers": {"A": "1.00"}
        }

        stdout, stderr, returncode = self.run_csv(csv_content)

        # Should succeed
        self.assertEqual(returncode, 0, f"Expected success (rc=0), got rc={returncode}. Stderr: {stderr}")
        # Stdout should be valid JSON matching expected
        try:
            output = json.loads(stdout)
        except json.JSONDecodeError:
            self.fail(f"Stdout is not valid JSON: {stdout}")

        self.assertEqual(output, expected, f"Output mismatch. Got: {output}")

    def test_three_fractional_digits_error(self):
        """Case: 3 fractional digits in amount should result in an error."""
        csv_content = "invoice_id,customer,amount,status\n1,A,1.001,paid\n"

        stdout, stderr, returncode = self.run_csv(csv_content)

        # Should fail
        self.assertNotEqual(returncode, 0, f"Expected error (rc!=0), got rc={returncode}")
        # Stdout should be empty
        self.assertEqual(stdout.strip(), "", f"Expected empty stdout on error, got: '{stdout}'")
        # Stderr should be non-empty
        self.assertTrue(len(stderr.strip()) > 0, "Expected non-empty stderr on error")

    def test_empty_no_header_error(self):
        """Case: Empty file with no header should result in an error."""
        csv_content = ""

        stdout, stderr, returncode = self.run_csv(csv_content)

        # Should fail
        self.assertNotEqual(returncode, 0, f"Expected error (rc!=0), got rc={returncode}")
        # Stdout should be empty
        self.assertEqual(stdout.strip(), "", f"Expected empty stdout on error, got: '{stdout}'")
        # Stderr should be non-empty
        self.assertTrue(len(stderr.strip()) > 0, "Expected non-empty stderr on error")

if __name__ == '__main__':
    unittest.main()
