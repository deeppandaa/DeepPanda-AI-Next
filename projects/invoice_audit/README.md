# Invoice Audit CLI

A local CSV invoice-audit tool for small businesses.

## Usage

```bash
python app.py input.csv
```

## Output

Prints a single JSON object to stdout:

```json
{
  "unique_invoices": 10,
  "duplicates_ignored": 2,
  "total": "1500.00",
  "customers": {
    "Alice": "500.00",
    "Bob": "1000.00"
  }
}
```

## Input Format

CSV with headers: `invoice_id`, `customer`, `amount`, `status`.
- `status`: `paid` or `refunded`.
- `amount`: Non-negative decimal, max 2 fractional digits.

## Errors

Exits with nonzero code and stderr message on:
- Missing file
- Invalid status
- Malformed amount
- Conflicting invoice IDs
- Missing required columns

## Verification status: incomplete acceptance

The local `qwen3.6:latest` model authored the implementation and original
12 tests from a requirements-only prompt. The supervising assistant did not
write or manually repair the application code.

The original tests passed twice, but independent contract inputs revealed
three defects. A second local model attempted acceptance-test generation;
its first versions had invalid quoting/missing imports/missing fixtures and
were not accepted as verification. Qwen3.6 generated the final three regression
tests from the required input/output cases, without supervisor-written test code.

The integrated repair loop then ran the actual 15 tests, obtained advisory
diagnoses from `qwen2.5-coder:7b`, and asked Qwen3.6 to fix implementation only.
Two approved updates reduced failures from three to two to one.
Both test files remained byte-for-byte unchanged during repair.
The loop stopped at its two-repair limit and did not declare success.

**Historical defect (now repaired by the local model):** whitespace-normalized
identical invoices were incorrectly rejected as conflicting. Reproduction:

```csv
invoice_id,customer,amount,status
 1 , A , 1.00 , paid
1,A,1.00,paid
```

Required: one unique invoice, one ignored duplicate, total `1.00`.
Before repair: nonzero exit with a conflict error; the initial bounded loop ended
at 14/15 tests and 14/15 independent behavior cases without claiming success.

The supervisor subsequently improved generic source-grounded review, structured
failure evidence and repair history, and fixed an observed planner context-budget
exhaustion. The original 8192-token context consumed 7053 input tokens and stopped
after 1138 output tokens (`done_reason=length`), cutting the full-file proposal.
Argument planning now uses a 16384-token context; truncated completions are
explicitly rejected rather than reported as generic invalid JSON.

A fresh actual `qwen3.8:latest` review cited the raw stored row and normalized
comparison. `qwen3.6:latest` produced one approved implementation-only update
(`9bca12fed52d425b9fcac69dd26bba12`). The supervisor did not write the application
fix or supply its concrete solution to either model.

**Verified result:** the unchanged 15 tests passed twice, in separately approved
managed runs (`03aa1e3dd98a462bbd65d9390134819c`,
`251b3b57fab641888de3e7168b23b78f`). All original 15 exact CLI cases and 60 further
whitespace-field/status/input-order permutations passed (75/75).
Both test-file hashes stayed unchanged throughout repair. This is bounded
evidence, not a production-readiness guarantee or a packaged delivery.

Some original model tests launch `app.py` relative to the working directory;
use the approved `project_test` action for the authoritative managed run.
In Qt select `project_test`, project `invoice_audit`, and approve the preview.
Model generation/review requests, observed cases and actual results are recorded
locally under `data\program-builds\invoice-autonomous-acceptance.json`.
Later diagnosis, real reports, immutable hashes and all 75 final inputs/results
are recorded in `data\program-builds\invoice-grounded-repair.json`.
See [MASTER_PLAN](../../MASTER_PLAN.md) for exact evidence and boundaries.
