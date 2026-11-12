#!/usr/bin/env python3
import argparse
import json
import sys

def main():
    parser = argparse.ArgumentParser(description='Report statistics from a JSON array of integers.')
    parser.add_argument('input_file', help='Path to the input JSON file')
    args = parser.parse_args()

    try:
        with open(args.input_file, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("Error: File not found.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error: Invalid JSON.", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        print("Error: Input must be a JSON array.", file=sys.stderr)
        sys.exit(1)

    for item in data:
        if isinstance(item, bool) or not isinstance(item, int):
            print("Error: Array contains non-integer values.", file=sys.stderr)
            sys.exit(1)

    if len(data) == 0:
        result = {"count": 0, "total": 0, "minimum": None, "maximum": None}
    else:
        count = len(data)
        total = sum(data)
        minimum = min(data)
        maximum = max(data)
        result = {"count": count, "total": total, "minimum": minimum, "maximum": maximum}

    print(json.dumps(result))

if __name__ == '__main__':
    main()
