import sqlite3

class Inventory:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS inventory
                         (name TEXT PRIMARY KEY, quantity INTEGER)''')
        self.conn.commit()

    def add(self, name, quantity):
        if quantity < 0:
            raise ValueError('Negative quantity not allowed')
        self.cursor.execute('''INSERT INTO inventory (name, quantity)
                             VALUES (?, ?)
                             ON CONFLICT(name) DO UPDATE
                             SET quantity = inventory.quantity + excluded.quantity''', (name, quantity))
        self.conn.commit()

    def search(self, name):
        self.cursor.execute('''SELECT quantity FROM inventory WHERE name = ?''', (name,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def close(self):
        self.conn.close()