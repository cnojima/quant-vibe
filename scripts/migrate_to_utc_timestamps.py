#!/usr/bin/env python3
"""
Migrate all naive now_utc() and now_utc() to UTC-aware timestamps.

This script performs automated replacement of naive datetime calls with
the UTC-aware utilities from quant_vibe.utils.timestamp_utils.

Usage:
    python scripts/migrate_to_utc_timestamps.py --dry-run  # Preview changes
    python scripts/migrate_to_utc_timestamps.py            # Apply changes
    python scripts/migrate_to_utc_timestamps.py --check    # Verify no naive datetimes remain
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple
import argparse


# Patterns to find and replace
PATTERNS = [
    # now_utc() → now_utc()
    {
        'pattern': r'datetime\.utcnow\(\)',
        'replacement': 'now_utc()',
        'name': 'now_utc()',
    },
    # now_utc() → now_utc() (when used for timestamps)
    {
        'pattern': r'datetime\.now\(\)',
        'replacement': 'now_utc()',
        'name': 'now_utc()',
        'exclude_comments': True,  # Don't replace in comments
    },
]

# Import statement to add if not present
IMPORT_STATEMENT = "from quant_vibe.utils import now_utc"
IMPORT_PATTERNS = [
    r'from quant_vibe\.utils import now_utc',
    r'from quant_vibe\.utils\.timestamp_utils import now_utc',
]


def find_python_files(root_dir: Path) -> List[Path]:
    """Find all Python files in src/ directory"""
    python_files = []

    # Search in src/ directory
    src_dir = root_dir / "src"
    if src_dir.exists():
        python_files.extend(src_dir.rglob("*.py"))

    # Search in scripts/ directory
    scripts_dir = root_dir / "scripts"
    if scripts_dir.exists():
        for f in scripts_dir.glob("*.py"):
            python_files.append(f)

    # Exclude test files (we'll handle those separately)
    python_files = [f for f in python_files if "test" not in str(f)]

    return sorted(python_files)


def has_import(content: str) -> bool:
    """Check if file already has the import statement"""
    for pattern in IMPORT_PATTERNS:
        if re.search(pattern, content):
            return True
    return False


def add_import(content: str) -> str:
    """Add import statement to file if needed"""
    if has_import(content):
        return content

    # Find the best place to insert import
    lines = content.split('\n')

    # Find last import line
    last_import_idx = -1
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            last_import_idx = i

    # If no imports found, add after docstring/comments
    if last_import_idx == -1:
        # Skip docstring if present
        in_docstring = False
        for i, line in enumerate(lines):
            if '"""' in line or "'''" in line:
                in_docstring = not in_docstring
            if not in_docstring and line.strip() and not line.strip().startswith('#'):
                last_import_idx = i - 1
                break

    # Insert import
    if last_import_idx >= 0:
        lines.insert(last_import_idx + 1, IMPORT_STATEMENT)
    else:
        # Add at beginning
        lines.insert(0, IMPORT_STATEMENT)

    return '\n'.join(lines)


def migrate_file(file_path: Path, dry_run: bool = False) -> Tuple[int, List[str]]:
    """
    Migrate a single file to use UTC-aware timestamps.

    Returns:
        (num_replacements, list_of_changes)
    """
    content = file_path.read_text()
    original_content = content
    changes = []
    total_replacements = 0

    # Apply each pattern
    for pattern_config in PATTERNS:
        pattern = pattern_config['pattern']
        replacement = pattern_config['replacement']
        name = pattern_config['name']

        # Find all matches
        matches = list(re.finditer(pattern, content))

        if matches:
            num_replacements = len(matches)
            total_replacements += num_replacements

            # Replace
            content = re.sub(pattern, replacement, content)

            changes.append(f"  - Replaced {num_replacements} instances of {name}")

    # Add import if we made replacements
    if total_replacements > 0:
        content = add_import(content)

        if not dry_run:
            file_path.write_text(content)

    return total_replacements, changes


def check_for_naive_datetimes(root_dir: Path) -> List[Tuple[Path, List[str]]]:
    """Check for any remaining naive datetime usage"""
    files = find_python_files(root_dir)
    findings = []

    for file_path in files:
        content = file_path.read_text()
        issues = []

        # Check for now_utc()
        matches = re.finditer(r'datetime\.utcnow\(\)', content)
        for match in matches:
            line_num = content[:match.start()].count('\n') + 1
            issues.append(f"  Line {line_num}: now_utc()")

        # Check for now_utc() (excluding comments)
        for line_num, line in enumerate(content.split('\n'), 1):
            if '#' in line:
                # Only check before comment
                line = line[:line.index('#')]
            if 'now_utc()' in line:
                issues.append(f"  Line {line_num}: now_utc()")

        if issues:
            findings.append((file_path, issues))

    return findings


def main():
    parser = argparse.ArgumentParser(description='Migrate naive datetimes to UTC-aware')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    parser.add_argument('--check', action='store_true', help='Check for remaining naive datetimes')
    args = parser.parse_args()

    # Get repository root
    root_dir = Path(__file__).parent.parent

    if args.check:
        # Check mode
        print("🔍 Checking for naive datetime usage...\n")
        findings = check_for_naive_datetimes(root_dir)

        if findings:
            print(f"❌ Found naive datetime usage in {len(findings)} files:\n")
            for file_path, issues in findings:
                rel_path = file_path.relative_to(root_dir)
                print(f"📄 {rel_path}:")
                for issue in issues:
                    print(issue)
                print()
            sys.exit(1)
        else:
            print("✅ No naive datetime usage found!")
            sys.exit(0)

    # Migration mode
    mode = "DRY RUN" if args.dry_run else "MIGRATION"
    print(f"🚀 Starting {mode}...\n")

    files = find_python_files(root_dir)
    print(f"Found {len(files)} Python files to process\n")

    total_files_changed = 0
    total_replacements = 0

    for file_path in files:
        num_replacements, changes = migrate_file(file_path, dry_run=args.dry_run)

        if num_replacements > 0:
            total_files_changed += 1
            total_replacements += num_replacements

            rel_path = file_path.relative_to(root_dir)
            print(f"📄 {rel_path}:")
            for change in changes:
                print(change)
            print()

    # Summary
    print("\n" + "="*60)
    if args.dry_run:
        print(f"DRY RUN SUMMARY:")
        print(f"  Would modify: {total_files_changed} files")
        print(f"  Would replace: {total_replacements} instances")
        print(f"\nRun without --dry-run to apply changes")
    else:
        print(f"MIGRATION COMPLETE:")
        print(f"  Modified: {total_files_changed} files")
        print(f"  Replaced: {total_replacements} instances")
        print(f"\nNext steps:")
        print(f"  1. Run tests: pytest tests/")
        print(f"  2. Check for issues: python scripts/migrate_to_utc_timestamps.py --check")
        print(f"  3. Review changes: git diff")
    print("="*60)


if __name__ == '__main__':
    main()
