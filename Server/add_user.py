# File: add_user.py
import os
import sqlite3

# Define the base directory for storing user-specific folders
BASE_DIR = os.path.join(os.getcwd(), "received")

def add_user(username, password):
    try:
        # Create the 'received' folder if it doesn't exist
        if not os.path.exists(BASE_DIR):
            os.makedirs(BASE_DIR)

        # Create a unique folder for the user
        user_folder = os.path.join(BASE_DIR, username)
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)

        # Connect to database
        connection = sqlite3.connect("users.db")
        cursor = connection.cursor()

        # Insert user data into the database
        cursor.execute("""
        INSERT INTO users (username, password, home_directory)
        VALUES (?, ?, ?)
        """, (username, password, user_folder))

        connection.commit()
        print(f"User '{username}' added successfully with home directory: {user_folder}")
    except sqlite3.IntegrityError:
        print(f"Error: User '{username}' already exists.")
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
    finally:
        connection.close()

if __name__ == "__main__":
    username = input("Enter username: ")
    password = input("Enter password: ")
    add_user(username, password)
