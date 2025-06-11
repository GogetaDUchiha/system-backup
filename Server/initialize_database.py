# File: initialize_database.py
import sqlite3

def create_database():
    try:
        # Connect to database
        connection = sqlite3.connect("users.db")
        cursor = connection.cursor()

        # Create the 'users' table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            home_directory TEXT NOT NULL
        )
        """)
        connection.commit()
        print("Database and 'users' table initialized successfully.")
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
    finally:
        connection.close()

if __name__ == "__main__":
    create_database()
