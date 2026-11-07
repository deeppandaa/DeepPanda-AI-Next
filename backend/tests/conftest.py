import os
import tempfile

# app.main builds the default app at import time; keep its state out of the real /data (C:\data on Windows).
os.environ.setdefault("AI_DATA_DIR", tempfile.mkdtemp(prefix="deeppanda-test-data-"))
