#!/usr/bin/env python3

"""
Password hash generator for users.json file.
Run this script to generate bcrypt password hashes for users.json.
"""

from passlib.context import CryptContext
import getpass
import json
import os

# Set up password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    """Generate a bcrypt hash from a password."""
    return pwd_context.hash(password)

def add_user_to_file(email, password, file_path="users.json"):
    """Add a new user to the users.json file."""
    # Create hashed password
    hashed_password = get_password_hash(password)
    
    # Create new user entry
    new_user = {
        "email": email,
        "hashed_password": hashed_password
    }
    
    # Load existing file or create new structure
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            if 'users' not in data:
                data['users'] = []
        except (json.JSONDecodeError, FileNotFoundError):
            data = {"users": []}
    else:
        data = {"users": []}
        
    # Check if user already exists
    for i, user in enumerate(data['users']):
        if user.get('email') == email:
            # Update existing user
            data['users'][i] = new_user
            print(f"Updated existing user: {email}")
            break
    else:
        # Add new user
        data['users'].append(new_user)
        print(f"Added new user: {email}")
        
    # Write back to file
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Users file updated at: {file_path}")

def main():
    print("===== User Password Hash Generator =====")
    print("This tool adds or updates users in the users.json file.")
    
    email = input("Enter user email: ").strip()
    if not email:
        print("Email cannot be empty.")
        return
        
    password = getpass.getpass("Enter password: ")
    confirm_password = getpass.getpass("Confirm password: ")
    
    if password != confirm_password:
        print("Passwords do not match.")
        return
        
    if not password:
        print("Password cannot be empty.")
        return
    
    file_path = input("Enter users file path [users.json]: ").strip() or "users.json"
    
    add_user_to_file(email, password, file_path)

if __name__ == "__main__":
    main()
