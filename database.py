import sqlite3
import bcrypt
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)
    hash_password = bcrypt.hashpw("password123".encode('utf-8'), bcrypt.gensalt())
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                  ("admin", hash_password))
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # User already exists
    conn.close()
init_db()