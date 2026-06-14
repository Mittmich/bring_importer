#!/usr/bin/env python3

"""
User management script for Recipe Parser API.
This script allows adding, removing, and listing users directly in the SQLite database.
"""

import argparse
import getpass
import os
import sqlite3
import sys

from passlib.context import CryptContext

# Set up password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Database setup
DB_PATH = "recipes.db"


def get_db_connection():
    """Connect to SQLite database and return connection."""
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file {DB_PATH} not found.")
        print("Make sure you're running this script from the correct directory.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_password_hash(password):
    """Generate bcrypt password hash."""
    return pwd_context.hash(password)


def add_user(email, password=None):
    """Add a new user or update an existing one."""
    if password is None:
        password = getpass.getpass("Enter password: ")
        confirm_password = getpass.getpass("Confirm password: ")

        if password != confirm_password:
            print("Error: Passwords do not match.")
            return False

        if not password:
            print("Error: Password cannot be empty.")
            return False

    # Hash the password
    hashed_password = get_password_hash(password)

    # Check if user exists
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    existing_user = cursor.fetchone()

    try:
        if existing_user:
            # Update existing user
            cursor.execute(
                "UPDATE users SET hashed_password = ? WHERE email = ?", (hashed_password, email)
            )
            print(f"Updated user: {email}")
        else:
            # Add new user
            cursor.execute(
                "INSERT INTO users (email, hashed_password) VALUES (?, ?)", (email, hashed_password)
            )
            print(f"Added user: {email}")

        conn.commit()
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        conn.close()


def remove_user(email):
    """Remove a user from the database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()

        if not user:
            print(f"User not found: {email}")
            return False

        # Check if user has recipes
        cursor.execute("SELECT COUNT(*) FROM recipes WHERE user_id = ?", (user["id"],))
        recipe_count = cursor.fetchone()[0]

        if recipe_count > 0:
            print(f"Warning: User has {recipe_count} recipes.")
            confirm = input("Delete user and all their recipes? (y/N): ").lower()

            if confirm != "y":
                print("Aborted.")
                return False

            # Delete recipes first (due to foreign key constraint)
            cursor.execute("DELETE FROM recipes WHERE user_id = ?", (user["id"],))
            print(f"Deleted {recipe_count} recipes.")

        # Delete user
        cursor.execute("DELETE FROM users WHERE id = ?", (user["id"],))
        print(f"Removed user: {email}")

        conn.commit()
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        conn.close()


def list_users():
    """List all users in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT u.id, u.email, COUNT(r.uuid) as recipe_count 
            FROM users u 
            LEFT JOIN recipes r ON u.id = r.user_id 
            GROUP BY u.id, u.email
            ORDER BY u.email
        """
        )
        users = cursor.fetchall()

        if not users:
            print("No users found.")
            return

        print("\n{:<5} {:<30} {:<10}".format("ID", "Email", "# Recipes"))
        print("-" * 50)

        for user in users:
            print("{:<5} {:<30} {:<10}".format(user["id"], user["email"], user["recipe_count"]))

        print("\nTotal users:", len(users))
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()


def check_db():
    """Check if database exists and has the required tables."""
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file {DB_PATH} not found.")
        return False

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check for users table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
        if not cursor.fetchone():
            print("Error: 'users' table not found in database.")
            conn.close()
            return False

        conn.close()
        return True
    except Exception as e:
        print(f"Error checking database: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Manage users for Recipe Parser API. Each user can attach an "
            "optional free-form 'note' to their saved recipes (see the "
            "'note' column on the recipes table); the script manages the "
            "user accounts only."
        )
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Add user command
    add_parser = subparsers.add_parser("add", help="Add a new user or update existing user")
    add_parser.add_argument("email", help="User email")
    add_parser.add_argument("-p", "--password", help="User password (will prompt if not provided)")

    # Remove user command
    remove_parser = subparsers.add_parser("remove", help="Remove a user")
    remove_parser.add_argument("email", help="User email to remove")

    # List users command
    subparsers.add_parser("list", help="List all users")

    args = parser.parse_args()

    # Check database before proceeding
    if not check_db():
        sys.exit(1)

    if args.command == "add":
        add_user(args.email, args.password)
    elif args.command == "remove":
        remove_user(args.email)
    elif args.command == "list":
        list_users()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
