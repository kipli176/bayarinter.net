import sqlite3

def get_db():
    conn = sqlite3.connect('langganan.sqlite3')
    conn.row_factory = sqlite3.Row
    return conn
