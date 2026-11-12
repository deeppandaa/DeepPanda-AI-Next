# Stok Demo

This is a simple inventory management system implemented in Python using SQLite.

## Usage

1. Create an instance of the `Inventory` class with a database path.
2. Use the `add` method to add items to the inventory.
3. Use the `search` method to retrieve the quantity of an item.
4. Use the `close` method to close the database connection.

## Verification and provenance

The local model created these files. Its repair attempts did not fix the
repeated-addition bug. The coding assistant corrected the SQL upsert manually;
this is not evidence of an autonomous model success.

Use the Qt `project_test` action for `stok_demo` to run the four generated tests
in the dedicated environment. `add` accumulates quantity, rejects negatives,
and `search` returns `None` when the product is absent.