# Stock Generated

A simple CLI inventory system using SQLite.

## Usage

```bash
python app.py --db <path_to_db> add <name> <quantity>
python app.py --db <path_to_db> get <name>
```

## Dependencies

Standard library only (sqlite3, argparse, json, subprocess, tempfile).