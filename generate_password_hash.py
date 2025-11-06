#!/usr/bin/env python3
"""
Utility script to generate bcrypt password hash for super admin authentication.
Usage: python3 generate_password_hash.py
"""

import bcrypt
import getpass

def generate_hash():
    """Generate a bcrypt hash for the super admin password."""
    print("=== Jeeves Super Admin Password Hash Generator ===\n")
    print("This will generate a bcrypt hash for your super admin password.")
    print("Add the resulting hash to config.yaml under core.super_admin_password_hash\n")

    while True:
        password = getpass.getpass("Enter super admin password: ")
        confirm = getpass.getpass("Confirm password: ")

        if password != confirm:
            print("Passwords do not match. Please try again.\n")
            continue

        if len(password) < 8:
            print("Password must be at least 8 characters. Please try again.\n")
            continue

        break

    # Generate salt and hash
    salt = bcrypt.gensalt(rounds=12)
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)

    print("\n" + "=" * 70)
    print("Generated hash (add this to config.yaml):")
    print("=" * 70)
    print(password_hash.decode('utf-8'))
    print("=" * 70)
    print("\nExample config.yaml entry:")
    print("core:")
    print("  super_admin_password_hash: \"" + password_hash.decode('utf-8') + "\"")
    print("  super_admin_session_hours: 1  # Optional: session expiry time")
    print("\nKeep this hash secure! Anyone with access to it can verify passwords.")

if __name__ == "__main__":
    try:
        generate_hash()
    except KeyboardInterrupt:
        print("\n\nCancelled.")
    except Exception as e:
        print(f"\nError: {e}")
