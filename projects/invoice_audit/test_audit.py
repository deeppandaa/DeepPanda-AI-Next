import unittest
import subprocess
import json
import tempfile
import os

class TestInvoiceAudit(unittest.TestCase):

    def run_app(self, csv_content):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
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

    def test_valid_single_paid(self):
        csv_data = "invoice_id,customer,amount,status\n1,Cust A,100.50,paid"
        res = self.run_app(csv_data)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data['unique_invoices'], 1)
        self.assertEqual(data['duplicates_ignored'], 0)
        self.assertEqual(data['total'], '100.50')
        self.assertEqual(data['customers'], {'Cust A': '100.50'})

    def test_valid_single_refunded(self):
        csv_data = "invoice_id,customer,amount,status\n1,Cust B,50.00,refunded"
        res = self.run_app(csv_data)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data['total'], '-50.00')
        self.assertEqual(data['customers'], {'Cust B': '-50.00'})

    def test_multiple_customers_sorted(self):
        csv_data = "invoice_id,customer,amount,status\n1,Zebra,10.00,paid\n2,Alpha,20.00,paid"
        res = self.run_app(csv_data)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(list(data['customers'].keys()), ['Alpha', 'Zebra'])

    def test_duplicates_ignored(self):
        csv_data = "invoice_id,customer,amount,status\n1,Cust A,100.00,paid\n1,Cust A,100.00,paid"
        res = self.run_app(csv_data)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data['unique_invoices'], 1)
        self.assertEqual(data['duplicates_ignored'], 1)

    def test_conflicting_duplicates_error(self):
        csv_data = "invoice_id,customer,amount,status\n1,Cust A,100.00,paid\n1,Cust B,50.00,paid"
        res = self.run_app(csv_data)
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), '')

    def test_malformed_amount(self):
        csv_data = "invoice_id,customer,amount,status\n1,Cust A,abc,paid"
        res = self.run_app(csv_data)
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), '')

    def test_invalid_status(self):
        csv_data = "invoice_id,customer,amount,status\n1,Cust A,100.00,pending"
        res = self.run_app(csv_data)
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), '')

    def test_missing_file(self):
        res = subprocess.run(['python', 'app.py', 'nonexistent.csv'], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), '')

    def test_empty_csv_with_header(self):
        csv_data = "invoice_id,customer,amount,status"
        res = self.run_app(csv_data)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data['unique_invoices'], 0)
        self.assertEqual(data['total'], '0.00')
        self.assertEqual(data['customers'], {})

    def test_exact_decimal_addition(self):
        csv_data = "invoice_id,customer,amount,status\n1,Cust A,0.10,paid\n2,Cust A,0.20,paid"
        res = self.run_app(csv_data)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        # Decimal addition should be exact
        self.assertEqual(data['customers']['Cust A'], '0.30')

    def test_quoted_customer_name(self):
        csv_data = 'invoice_id,customer,amount,status\n1,"Smith, John",100.00,paid'
        res = self.run_app(csv_data)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIn('Smith, John', data['customers'])

    def test_bom_utf8(self):
        csv_data = "invoice_id,customer,amount,status\n1,Cust A,10.00,paid"
        # Add BOM manually
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as f:
            f.write(b'\xef\xbb\xbf')
            f.write(csv_data.encode('utf-8'))
            temp_path = f.name
        try:
            res = subprocess.run(['python', 'app.py', temp_path], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)
            data = json.loads(res.stdout)
            self.assertEqual(data['unique_invoices'], 1)
        finally:
            os.unlink(temp_path)

if __name__ == '__main__':
    unittest.main()
