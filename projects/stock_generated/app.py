import argparse
import json
import sys
from inventory import Inventory

def main():
    parser = argparse.ArgumentParser(description='Stock CLI')
    parser.add_argument('--db', required=True, help='Database path')
    subparsers = parser.add_subparsers(dest='command')

    add_parser = subparsers.add_parser('add')
    add_parser.add_argument('name', type=str)
    add_parser.add_argument('quantity', type=int)

    get_parser = subparsers.add_parser('get')
    get_parser.add_argument('name', type=str)

    args = parser.parse_args()
    inv = Inventory(args.db)
    try:
        if args.command == 'add':
            try:
                inv.add(args.name, args.quantity)
                qty = inv.search(args.name)
                print(json.dumps({"name": args.name, "quantity": qty}))
            except ValueError as e:
                print(str(e), file=sys.stderr)
                sys.exit(1)
        elif args.command == 'get':
            qty = inv.search(args.name)
            print(json.dumps({"name": args.name, "quantity": qty}))
    finally:
        inv.close()

if __name__ == '__main__':
    main()