#!/usr/bin/env python3
"""Quick test script to verify models API structure."""

import sys
import ast

def check_file_syntax(filepath):
    """Check if a Python file has valid syntax."""
    try:
        with open(filepath, 'r') as f:
            ast.parse(f.read())
        print(f"✓ {filepath}: Valid syntax")
        return True
    except SyntaxError as e:
        print(f"✗ {filepath}: Syntax error - {e}")
        return False

files_to_check = [
    "src/models/settings.py",
    "src/services/model_provider.py",
    "src/services/user_settings.py",
    "src/api/routes/models.py",
]

print("Checking syntax of new files...")
all_valid = True
for filepath in files_to_check:
    if not check_file_syntax(filepath):
        all_valid = False

if all_valid:
    print("\n✓ All files have valid syntax!")
    sys.exit(0)
else:
    print("\n✗ Some files have syntax errors")
    sys.exit(1)
