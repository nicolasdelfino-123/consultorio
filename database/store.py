import sqlite3
from services.text_processor import term_key


class Store:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.create_collation('UNICODE_NOCASE', lambda a, b: (a.casefold() > b.casefold()) - (a.casefold() < b.casefold()))
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS rules (term TEXT PRIMARY KEY COLLATE UNICODE_NOCASE, replacement TEXT NOT NULL);
        ''')
        self.connection.commit()

    def get(self, key, default=''):
        row = self.connection.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def set(self, key, value):
        with self.connection:
            self.connection.execute('INSERT OR REPLACE INTO settings VALUES (?, ?)', (key, value))

    def rules(self):
        return self.connection.execute('SELECT term, replacement FROM rules ORDER BY term').fetchall()

    def find_rule(self, term):
        key = term_key(term)
        return next((rule for rule in self.rules() if term_key(rule[0]) == key), None)

    def add_rule(self, term, replacement):
        term, replacement = term.strip(), replacement.strip()
        if not term or not replacement:
            raise ValueError('Completá la palabra y su reemplazo.')
        if len(term) > 200 or len(replacement) > 200:
            raise ValueError('Cada campo admite hasta 200 caracteres.')
        with self.connection:
            for existing_term, _ in self.rules():
                if term_key(existing_term) == term_key(term):
                    self.connection.execute('DELETE FROM rules WHERE term=?', (existing_term,))
            self.connection.execute('INSERT OR REPLACE INTO rules VALUES (?, ?)', (term, replacement))

    def delete_rule(self, term):
        with self.connection:
            self.connection.execute('DELETE FROM rules WHERE term=?', (term,))

    def close(self):
        self.connection.close()
