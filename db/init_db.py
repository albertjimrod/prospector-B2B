import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipeline.db')
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')

def init():
    os.makedirs(os.path.normpath(os.path.dirname(DB_PATH)), exist_ok=True)
    with open(SCHEMA_PATH) as f:
        schema = f.read()
    conn = sqlite3.connect(os.path.normpath(DB_PATH))
    conn.executescript(schema)
    conn.close()
    print(f'Base de datos inicializada en {os.path.normpath(DB_PATH)}')

if __name__ == '__main__':
    init()
