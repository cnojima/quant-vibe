# Development Tools

This directory contains development tools and utilities for the quant-vibe project.

## Claude Code RAG System

The `claude_rag.py` tool provides a Retrieval-Augmented Generation (RAG) interface for querying and modifying the codebase using Claude API with prompt caching.

### Features

- **Full codebase context** via intelligent indexing and chunking
- **90% cheaper token costs** with prompt caching
- **Fast iteration** on complex changes
- **Better debugging** with complete context awareness
- **Smart chunking** by classes, functions, and file types

### Setup

1. **Install dependencies**:
   ```bash
   source venv/bin/activate
   pip install anthropic python-dotenv
   ```

2. **Get your Anthropic API key**:
   - Visit: https://console.anthropic.com/settings/keys
   - Create a new API key

3. **Add to `.env`**:
   ```bash
   ANTHROPIC_API_KEY=sk-ant-your-key-here
   ```

4. **Build the codebase index**:
   ```bash
   python tools/claude_rag.py --index
   ```

### Usage

#### Query the codebase

Ask questions or request information:

```bash
# Show specific code logic
python tools/claude_rag.py --query "Show me the current spread entry logic"

# Find patterns across codebase
python tools/claude_rag.py --query "Where are all the profit targets defined?"

# Understand architecture
python tools/claude_rag.py --query "Explain how the backtesting engine works"
```

#### Request code modifications

Ask for code changes (Claude will show you what to modify):

```bash
# Add functionality
python tools/claude_rag.py --query "Add logging to all entry decisions in strategies"

# Modify existing code
python tools/claude_rag.py --query "Modify stop loss to use 2x ATR instead of fixed percentage"

# Refactor
python tools/claude_rag.py --query "Refactor the options position tracking to use a dedicated class"
```

#### Rebuild the index

After making significant changes to the codebase:

```bash
python tools/claude_rag.py --index
```

### Advanced Options

```bash
# Disable caching (not recommended - 10x more expensive)
python tools/claude_rag.py --query "Your query" --no-cache

# Use different model
python tools/claude_rag.py --query "Your query" --model claude-opus-4-20250514

# Specify project root
python tools/claude_rag.py --query "Your query" --project-root /path/to/project

# Quiet mode (suppress progress messages)
python tools/claude_rag.py --query "Your query" --quiet
```

### How It Works

1. **Indexing**: The tool walks through your codebase and creates intelligent chunks:
   - Python files are split by classes and functions
   - Other files are chunked by size
   - Metadata is extracted (file path, line numbers, chunk type)
   - Index is cached in `.rag_cache/index.json`

2. **Context Building**: When you query:
   - Loads the cached index
   - Prioritizes important files (strategies, backtesting, configs)
   - Builds a context string with top N chunks
   - Marks context as cacheable for cost savings

3. **Querying**:
   - Sends context + query to Claude API
   - Uses prompt caching to reduce costs by ~90%
   - Returns Claude's analysis or recommendations
   - Shows token usage and cache savings

### Cost Optimization

The RAG system uses Claude's prompt caching feature:

- **Without caching**: Every query pays full price for all tokens
- **With caching**: Context is cached after first use
  - First query: ~10,000 input tokens
  - Subsequent queries: ~100 input tokens + cache read (90% cheaper)

Example costs (approximate):
- Without caching: $0.15 per query
- With caching: $0.015 per query (after first)
- **Savings: ~90% on repeated queries**

### What Gets Indexed

**Included**:
- Python files (`.py`)
- Config files (`.yaml`, `.yml`, `.json`)
- Documentation (`.md`, `.txt`)
- Scripts (`.sh`, `.sql`)

**Excluded**:
- Virtual environments (`venv`, `.venv`)
- Cache directories (`__pycache__`, `.pytest_cache`)
- Git metadata (`.git`)
- Build artifacts (`dist`, `build`, `*.pyc`)
- Logs and secrets (`.log`, `.env`)
- Node modules, Python eggs, etc.

### Examples

#### 1. Understanding existing code

```bash
python tools/claude_rag.py --query "How does the BullishVerticalPutStrategy decide when to enter a trade?"
```

Response will show:
- The relevant strategy code
- Entry logic explanation
- Market conditions checked
- Parameter usage

#### 2. Finding implementation patterns

```bash
python tools/claude_rag.py --query "Show me all places where we calculate Greeks"
```

Response will identify:
- All files that use Greeks
- Different calculation methods
- Where Greeks are stored/used

#### 3. Requesting modifications

```bash
python tools/claude_rag.py --query "Add debug logging before and after every options trade entry. Show me exactly what to add to each strategy file."
```

Response will provide:
- Specific code changes needed
- Line numbers and file paths
- Complete code snippets to add
- Explanation of changes

#### 4. Debugging issues

```bash
python tools/claude_rag.py --query "Why might the backtester be calculating profit/loss incorrectly for multi-leg spreads?"
```

Response will analyze:
- Relevant backtesting code
- P&L calculation logic
- Potential bugs or edge cases
- Suggested fixes

### Tips for Best Results

1. **Be specific**: "Show me the stop loss logic in BullishVerticalPutStrategy" is better than "Show me stop loss"

2. **Request complete solutions**: "Add error handling to all API calls and show me the exact code changes" gets you actionable results

3. **Rebuild index after major changes**: If you've added/removed many files, run `--index` again

4. **Use for complex queries**: The RAG system shines when you need context from multiple files

5. **Iterate quickly**: Cache makes follow-up questions very cheap, so ask clarifying questions freely

### Troubleshooting

**"ANTHROPIC_API_KEY not set"**
- Check that you've added the key to `.env`
- Make sure the key doesn't have quotes around it
- Verify the key is valid at https://console.anthropic.com

**"No index found"**
- Run `python tools/claude_rag.py --index` first
- Check that `.rag_cache/index.json` was created

**Query returns irrelevant results**
- Try being more specific in your query
- Rebuild the index if codebase changed significantly
- The system prioritizes strategies/backtesting - other code may be lower priority

**"Rate limit exceeded"**
- Wait a moment and try again
- You may have exceeded your Anthropic API quota
- Check your usage at https://console.anthropic.com

### Architecture

```
claude_rag.py
├── ClaudeCodeRAG (main class)
│   ├── index_codebase() - Walk codebase and create chunks
│   ├── chunk_python_file() - Smart chunking for Python
│   ├── chunk_generic_file() - Chunking for other files
│   ├── build_context() - Create prompt from chunks
│   ├── query() - Send query to Claude with caching
│   ├── _save_index() - Cache index to disk
│   └── _load_index() - Load cached index
├── CodeChunk (dataclass) - Represents a code chunk
└── main() - CLI entry point
```

### Future Enhancements

Potential improvements:

- **Vector embeddings**: Use semantic search instead of priority-based selection
- **Interactive mode**: Chat-style interface with conversation history
- **Auto-apply changes**: Automatically modify files based on Claude's suggestions
- **Custom chunking strategies**: Tune chunking per file type
- **Selective indexing**: Index only specific directories
- **Diff mode**: Show git diff of suggested changes

### Related Documentation

- [Claude API Documentation](https://docs.anthropic.com/claude/docs)
- [Prompt Caching Guide](https://docs.anthropic.com/claude/docs/prompt-caching)
- [Project Documentation](../CLAUDE.md)
