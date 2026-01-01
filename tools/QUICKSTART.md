# Claude RAG Quick Start

Get started with the RAG system in 3 steps:

## 1. Setup (One-Time)

```bash
# Install dependencies
source venv/bin/activate
pip install anthropic python-dotenv

# Your API key is already in .env
# If not, add: ANTHROPIC_API_KEY=sk-ant-your-key-here
```

## 2. Build Index (First Time)

```bash
python tools/claude_rag.py --index
```

This scans your codebase and creates a searchable index. Takes ~10 seconds.

## 3. Start Querying

### Ask Questions

```bash
# Understand code
python tools/claude_rag.py --query "How does the backtesting engine work?"

# Find implementations
python tools/claude_rag.py --query "Where is stop loss logic implemented?"

# Get code details
python tools/claude_rag.py --query "Show me all profit target calculations"
```

### Request Changes

```bash
# Add features
python tools/claude_rag.py --query "Add error logging to all strategy entry points. Show me the exact code to add."

# Modify existing code
python tools/claude_rag.py --query "Change the default profit target from 50% to 70% in all strategies"

# Debug issues
python tools/claude_rag.py --query "Why might the P&L calculation be wrong for spreads?"
```

## Cost Savings

- **First query**: Creates cache (~$0.15)
- **Following queries**: Use cache (~$0.015 each)
- **Savings**: ~90% on repeated queries

The cache lasts 5 minutes, so ask follow-up questions quickly!

## Tips

1. **Be specific**: Include file names or strategy names when possible
2. **Ask for code**: Request "show me the exact code" to get actionable results
3. **Follow up**: Cache makes follow-up questions very cheap
4. **Rebuild index**: Run `--index` after major code changes

## Example Session

```bash
# Build index (first time only)
$ python tools/claude_rag.py --index
Indexing complete: 315 files, 1,758 chunks

# First query (creates cache)
$ python tools/claude_rag.py --query "What strategies are implemented?"
Token usage: 14,520 cache creation + 18 input

# Follow-up query (uses cache - 99.9% savings!)
$ python tools/claude_rag.py --query "Show me the BullishVerticalPut entry logic"
Token usage: 14,520 cache read + 23 input
Cache savings: ~99.9%
```

## Full Documentation

See [README.md](README.md) for complete documentation, advanced usage, and troubleshooting.
