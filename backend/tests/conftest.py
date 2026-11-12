import os
import tempfile
from pathlib import Path

# app.main builds the default app at import time; keep test state inside the F: workspace.
test_data_root = Path(__file__).resolve().parents[2] / "_tmp" / "test-data"
test_data_root.mkdir(parents=True, exist_ok=True)
os.environ["AI_DATA_DIR"] = tempfile.mkdtemp(prefix="deeppanda-", dir=test_data_root)
