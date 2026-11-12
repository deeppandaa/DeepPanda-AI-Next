import sqlite3

class Inventory:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.cursor.execute(
            'CREATE TABLE IF NOT EXISTS items (name TEXT PRIMARY KEY, quantity INTEGER)'
        )

    def add(self, name, quantity):
        if quantity < 0:
            raise ValueError("Quantity cannot be negative")
        self.cursor.execute(
            'INSERT INTO items (name, quantity) VALUES (?, ?) '
            'ON CONFLICT(name) DO UPDATE SET quantity = items.quantity + ?',
            (name, quantity, quantity)
        )
        self.conn.commit()

    def search(self, name):
        self.cursor.execute('SELECT quantity FROM items WHERE name = ?', (name,))
        row = self.cursor.fetchone()
        return row[0] if row else None

    def close(self):
        self.conn.close()