#!/usr/bin/env python3
import sys
import csv
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

def main():
    if len(sys.argv) != 2:
        print("Usage: python app.py <input.csv>", file=sys.stderr)
        sys.exit(1)

    input_file = sys.argv[1]

    try:
        with open(input_file, 'r', encoding='utf-8-sig') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: File '{input_file}' not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)

    # Check for empty content first
    if not content.strip():
        print("Error: Empty CSV or no header.", file=sys.stderr)
        sys.exit(1)

    reader = csv.DictReader(content.splitlines())

    # Check for required columns
    if reader.fieldnames is None:
        print("Error: Empty CSV or no header.", file=sys.stderr)
        sys.exit(1)

    required_cols = {'invoice_id', 'customer', 'amount', 'status'}
    actual_cols = set(reader.fieldnames)
    if not required_cols.issubset(actual_cols):
        missing = required_cols - actual_cols
        print(f"Error: Missing columns: {missing}", file=sys.stderr)
        sys.exit(1)

    seen_ids = {}
    duplicates_ignored = 0
    total_amount = Decimal('0')
    customer_totals = {}
    valid_rows_count = 0

    for row_num, row in enumerate(reader, start=2):
        invoice_id = row.get('invoice_id', '').strip()
        customer = row.get('customer', '').strip()
        amount_str = row.get('amount', '').strip()
        status = row.get('status', '').strip().lower()

        # Validate non-empty fields
        if not invoice_id or not customer or not amount_str or not status:
            print(f"Error: Row {row_num} has empty required fields.", file=sys.stderr)
            sys.exit(1)

        # Validate status
        if status not in ('paid', 'refunded'):
            print(f"Error: Row {row_num} has invalid status '{status}'.", file=sys.stderr)
            sys.exit(1)

        # Validate amount
        try:
            amount = Decimal(amount_str)
        except InvalidOperation:
            print(f"Error: Row {row_num} has malformed amount '{amount_str}'.", file=sys.stderr)
            sys.exit(1)

        if amount < 0:
            print(f"Error: Row {row_num} has negative amount.", file=sys.stderr)
            sys.exit(1)

        # Check for exponent or infinity (Decimal handles this, but let's be explicit if needed)
        # Decimal('1E+2') is valid but we want fixed point. The prompt says "no exponent".
        # However, standard Decimal parsing of '100' doesn't produce exponent notation in repr usually.
        # Let's ensure it's a simple number.
        if 'e' in amount_str.lower() or 'inf' in amount_str.lower() or 'nan' in amount_str.lower():
             print(f"Error: Row {row_num} has invalid amount format.", file=sys.stderr)
             sys.exit(1)

        # Check for 3 fractional digits
        if '.' in amount_str:
            decimal_part = amount_str.split('.')[1]
            if len(decimal_part) > 2:
                print(f"Error: Row {row_num} has invalid amount format (too many decimal places).", file=sys.stderr)
                sys.exit(1)

        # Normalize amount to 2 decimal places for storage/comparison if needed,
        # but keep precision for calculation. The output requires 2 places.
        # We will sum exact Decimals and round at the end.

        # Check for duplicates/conflicts
        # "Same invoice_id with identical normalized row appears once; conflicting row with same ID is an error."
        if invoice_id in seen_ids:
            prev_row = seen_ids[invoice_id]
            # Normalize current row for comparison
            curr_normalized = (invoice_id, customer, amount_str, status)
            prev_normalized = (prev_row['invoice_id'], prev_row['customer'], prev_row['amount'], prev_row['status'])

            if curr_normalized == prev_normalized:
                duplicates_ignored += 1
                continue
            else:
                print(f"Error: Row {row_num} conflicts with previous invoice_id '{invoice_id}'.", file=sys.stderr)
                sys.exit(1)

        # Store normalized values to ensure consistent comparison for future duplicates
        seen_ids[invoice_id] = {
            'invoice_id': invoice_id,
            'customer': customer,
            'amount': amount_str,
            'status': status
        }
        valid_rows_count += 1

        # Calculate totals
        if status == 'paid':
            total_amount += amount
            customer_totals[customer] = customer_totals.get(customer, Decimal('0')) + amount
        else: # refunded
            total_amount -= amount
            customer_totals[customer] = customer_totals.get(customer, Decimal('0')) - amount

    # Format output
    def fmt(d):
        return str(d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    sorted_customers = dict(sorted(customer_totals.items()))
    formatted_customers = {k: fmt(v) for k, v in sorted_customers.items()}

    result = {
        "unique_invoices": valid_rows_count,
        "duplicates_ignored": duplicates_ignored,
        "total": fmt(total_amount),
        "customers": formatted_customers
    }

    print(json.dumps(result))

if __name__ == '__main__':
    main()
