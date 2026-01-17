#!/usr/bin/env python3
"""Check the schema and constraints of the options_bars table."""

import os
import sys
from pathlib import Path
import psycopg2
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Local DB config
LOCAL_CONFIG = {
    'host': os.getenv('TIMESCALE_HOST', 'localhost'),
    'port': int(os.getenv('TIMESCALE_PORT', '5432')),
    'database': os.getenv('TIMESCALE_DB', 'options_data'),
    'user': os.getenv('TIMESCALE_USER', 'quantvibe'),
    'password': os.getenv('TIMESCALE_PASSWORD', 'quantvibe_dev')
}

def check_schema():
    """Check the options_bars table schema and constraints."""
    conn = psycopg2.connect(**LOCAL_CONFIG)

    try:
        with conn.cursor() as cur:
            # Check table columns
            print("=" * 70)
            print("OPTIONS_BARS TABLE COLUMNS:")
            print("=" * 70)
            cur.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'options_bars'
                ORDER BY ordinal_position;
            """)
            for row in cur.fetchall():
                print(f"  {row[0]:25} {row[1]:20} {row[2]}")

            # Check constraints
            print("\n" + "=" * 70)
            print("TABLE CONSTRAINTS:")
            print("=" * 70)
            cur.execute("""
                SELECT conname, contype,
                       pg_get_constraintdef(c.oid) as definition
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                WHERE t.relname = 'options_bars'
                ORDER BY conname;
            """)
            constraints = cur.fetchall()
            if constraints:
                for row in constraints:
                    print(f"  Name: {row[0]}")
                    print(f"  Type: {row[1]} ({get_constraint_type(row[1])})")
                    print(f"  Definition: {row[2]}")
                    print()
            else:
                print("  No constraints found!")

            # Check indexes
            print("=" * 70)
            print("TABLE INDEXES:")
            print("=" * 70)
            cur.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'options_bars'
                ORDER BY indexname;
            """)
            indexes = cur.fetchall()
            if indexes:
                for row in indexes:
                    print(f"  {row[0]}:")
                    print(f"    {row[1]}")
                    print()
            else:
                print("  No indexes found!")

    finally:
        conn.close()

def get_constraint_type(contype):
    """Get human-readable constraint type."""
    types = {
        'p': 'PRIMARY KEY',
        'f': 'FOREIGN KEY',
        'u': 'UNIQUE',
        'c': 'CHECK',
        'x': 'EXCLUSION'
    }
    return types.get(contype, 'UNKNOWN')

if __name__ == '__main__':
    check_schema()