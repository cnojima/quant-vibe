#!/bin/bash
# Activate virtual environment and set PYTHONPATH
source venv/bin/activate
export PYTHONPATH="${PYTHONPATH}:${PWD}/src"
echo "✓ Virtual environment activated"
echo "✓ PYTHONPATH set to include src/"
echo ""
echo "Available commands:"
echo "  pytest              - Run all tests"
echo "  pytest -v           - Run tests with verbose output"
echo "  black src/ tests/   - Format code"
echo "  ruff check src/     - Lint code"
echo "  mypy src/           - Type check code"
