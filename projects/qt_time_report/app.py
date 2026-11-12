import sys
import json
import re

def parse_time(time_str):
    if not isinstance(time_str, str):
        raise ValueError("Input must be a string")
    time_str = time_str.strip()
    # Use [0-9] to strictly match ASCII digits only, rejecting Unicode digits
    pattern = r'^([0-9]{2}):([0-9]{2})$'
    match = re.match(pattern, time_str)
    if not match:
        raise ValueError(f"Invalid format: {time_str}")
    hours = int(match.group(1))
    minutes = int(match.group(2))
    if hours > 99 or minutes > 59:
        raise ValueError(f"Invalid time: {time_str}")
    return hours * 60 + minutes

def process_times(input_file):
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{input_file}' not found.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error: Malformed JSON.", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        print("Error: Root must be an array.", file=sys.stderr)
        sys.exit(1)

    total_minutes = 0
    longest_minutes = 0
    count = len(data)

    for item in data:
        try:
            minutes = parse_time(item)
            total_minutes += minutes
            if minutes > longest_minutes:
                longest_minutes = minutes
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    result = {
        "count": count,
        "total_minutes": total_minutes,
        "longest_minutes": longest_minutes
    }
    print(json.dumps(result))

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python app.py <input.json>", file=sys.stderr)
        sys.exit(1)
    process_times(sys.argv[1])