# Local repair acceptance

The coding assistant supplied an intentionally faulty SQLite implementation and
six fixed unittest tests. The faulty upsert replaced the stored quantity instead
of adding to it. Initial execution: six tests, two failures.

The actual local `qwen3.6:latest` model repaired only `inventory.py`, through the
normal agent planner and separately approved Windows host update. The subsequent
real test run passed all six tests. No coding-assistant source fix was applied.
The complete test file remained byte-for-byte unchanged:
SHA-256 `645dda8486602094db44b37d9f9a796f2763d4f5d7f02a89cfd3ce2423e474e9`.

The tests cover accumulation, zero and negative quantities, missing items,
SQL-special product names and SQLite persistence after reopening.

This demonstrates one bounded local model repair, not autonomous creation from
a description, general repair reliability, or EXE delivery.
See [the repair evidence](../../MASTER_PLAN.md#c3-gerçek-kanıtlı-yerel-model-düzeltmesi)
for operation IDs and the limits of this acceptance.
