#!/usr/bin/env python3
"""
Claude Code RAG (Retrieval-Augmented Generation) System

This tool provides a RAG interface for querying and modifying the codebase using Claude API
with prompt caching for 90% cost reduction on repeated queries.

Features:
- Full codebase context via prompt caching
- Intelligent code chunking and indexing
- 90% cheaper token costs with caching
- Fast iteration on complex changes
- Better debugging with full context

Usage:
    python tools/claude_rag.py --query "Show me the current spread entry logic"
    python tools/claude_rag.py --query "Add logging to all entry decisions"
    python tools/claude_rag.py --query "Modify stop loss to use 2x ATR"
    python tools/claude_rag.py --index  # Rebuild codebase index
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import anthropic
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Error: Missing required dependency: {e}")
    print("Please install: pip install anthropic python-dotenv")
    sys.exit(1)


@dataclass
class CodeChunk:
    """Represents a chunk of code with metadata."""

    file_path: str
    content: str
    start_line: int
    end_line: int
    chunk_type: str  # 'class', 'function', 'module', 'config'
    name: Optional[str] = None


class ClaudeCodeRAG:
    """
    RAG system for development using Claude API with prompt caching.

    This class indexes the codebase, chunks it intelligently, and provides
    a query interface that uses Claude's prompt caching to reduce costs by ~90%.
    """

    # Files/directories to exclude from indexing
    EXCLUDE_PATTERNS = {
        "__pycache__",
        ".git",
        ".pytest_cache",
        "venv",
        "env",
        ".venv",
        "node_modules",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        "*.pyc",
        "*.pyo",
        "*.egg-info",
        ".DS_Store",
        "*.log",
        ".env",
        "tokens",
    }

    # File extensions to include
    INCLUDE_EXTENSIONS = {
        ".py",
        ".yaml",
        ".yml",
        ".md",
        ".sql",
        ".sh",
        ".txt",
        ".json",
    }

    # Maximum chunk size in characters
    MAX_CHUNK_SIZE = 8000

    def __init__(self, project_root: Path, api_key: Optional[str] = None):
        """
        Initialize the RAG system.

        Args:
            project_root: Root directory of the project
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        """
        self.project_root = Path(project_root)
        self.cache_dir = self.project_root / ".rag_cache"
        self.cache_dir.mkdir(exist_ok=True)

        # Load API key
        load_dotenv()
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key or self.api_key == "your-api-key-here":
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Please add it to .env file.\n"
                "Get your API key from: https://console.anthropic.com/settings/keys"
            )

        # Initialize Claude client
        self.client = anthropic.Anthropic(api_key=self.api_key)

        # Cache for indexed code
        self.code_chunks: List[CodeChunk] = []
        self.index_metadata: Dict = {}

    def should_exclude(self, path: Path) -> bool:
        """Check if a path should be excluded from indexing."""
        path_str = str(path)
        for pattern in self.EXCLUDE_PATTERNS:
            if pattern.startswith("*"):
                if path_str.endswith(pattern[1:]):
                    return True
            elif pattern in path_str:
                return True
        return False

    def should_include(self, path: Path) -> bool:
        """Check if a file should be included in indexing."""
        return path.suffix in self.INCLUDE_EXTENSIONS and not self.should_exclude(path)

    def chunk_python_file(self, file_path: Path, content: str) -> List[CodeChunk]:
        """
        Intelligently chunk a Python file by classes and functions.

        Args:
            file_path: Path to the Python file
            content: File contents

        Returns:
            List of CodeChunk objects
        """
        chunks = []
        lines = content.split("\n")

        # Simple heuristic: split on class/function definitions
        current_chunk = []
        current_start = 1
        current_type = "module"
        current_name = None

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Detect class or function
            if stripped.startswith("class ") or stripped.startswith("def "):
                # Save previous chunk if it exists
                if current_chunk:
                    chunk_content = "\n".join(current_chunk)
                    if len(chunk_content.strip()) > 0:
                        chunks.append(
                            CodeChunk(
                                file_path=str(file_path.relative_to(self.project_root)),
                                content=chunk_content,
                                start_line=current_start,
                                end_line=i - 1,
                                chunk_type=current_type,
                                name=current_name,
                            )
                        )

                # Start new chunk
                current_chunk = [line]
                current_start = i
                current_type = "class" if stripped.startswith("class ") else "function"

                # Extract name
                if stripped.startswith("class "):
                    current_name = stripped.split("class ")[1].split("(")[0].split(":")[0].strip()
                elif stripped.startswith("def "):
                    current_name = stripped.split("def ")[1].split("(")[0].strip()
            else:
                current_chunk.append(line)

            # Split if chunk gets too large
            if len("\n".join(current_chunk)) > self.MAX_CHUNK_SIZE:
                chunk_content = "\n".join(current_chunk)
                chunks.append(
                    CodeChunk(
                        file_path=str(file_path.relative_to(self.project_root)),
                        content=chunk_content,
                        start_line=current_start,
                        end_line=i,
                        chunk_type=current_type,
                        name=current_name,
                    )
                )
                current_chunk = []
                current_start = i + 1
                current_type = "module"
                current_name = None

        # Save final chunk
        if current_chunk:
            chunk_content = "\n".join(current_chunk)
            if len(chunk_content.strip()) > 0:
                chunks.append(
                    CodeChunk(
                        file_path=str(file_path.relative_to(self.project_root)),
                        content=chunk_content,
                        start_line=current_start,
                        end_line=len(lines),
                        chunk_type=current_type,
                        name=current_name,
                    )
                )

        return chunks

    def chunk_generic_file(self, file_path: Path, content: str) -> List[CodeChunk]:
        """
        Chunk a non-Python file into manageable pieces.

        Args:
            file_path: Path to the file
            content: File contents

        Returns:
            List of CodeChunk objects
        """
        # For small files, return as single chunk
        if len(content) <= self.MAX_CHUNK_SIZE:
            return [
                CodeChunk(
                    file_path=str(file_path.relative_to(self.project_root)),
                    content=content,
                    start_line=1,
                    end_line=len(content.split("\n")),
                    chunk_type="file",
                    name=file_path.name,
                )
            ]

        # For larger files, split by lines
        chunks = []
        lines = content.split("\n")
        current_chunk = []
        current_start = 1

        for i, line in enumerate(lines, start=1):
            current_chunk.append(line)

            if len("\n".join(current_chunk)) > self.MAX_CHUNK_SIZE:
                chunks.append(
                    CodeChunk(
                        file_path=str(file_path.relative_to(self.project_root)),
                        content="\n".join(current_chunk),
                        start_line=current_start,
                        end_line=i,
                        chunk_type="file",
                        name=file_path.name,
                    )
                )
                current_chunk = []
                current_start = i + 1

        # Save final chunk
        if current_chunk:
            chunks.append(
                CodeChunk(
                    file_path=str(file_path.relative_to(self.project_root)),
                    content="\n".join(current_chunk),
                    start_line=current_start,
                    end_line=len(lines),
                    chunk_type="file",
                    name=file_path.name,
                )
            )

        return chunks

    def index_codebase(self, verbose: bool = True) -> Tuple[int, int]:
        """
        Index the entire codebase into chunks.

        Args:
            verbose: Whether to print progress

        Returns:
            Tuple of (files_indexed, chunks_created)
        """
        if verbose:
            print(f"Indexing codebase at: {self.project_root}")

        files_indexed = 0
        chunks_created = 0
        self.code_chunks = []

        # Walk through project directory
        for file_path in self.project_root.rglob("*"):
            if not file_path.is_file() or not self.should_include(file_path):
                continue

            try:
                # Read file
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # Chunk based on file type
                if file_path.suffix == ".py":
                    chunks = self.chunk_python_file(file_path, content)
                else:
                    chunks = self.chunk_generic_file(file_path, content)

                self.code_chunks.extend(chunks)
                files_indexed += 1
                chunks_created += len(chunks)

                if verbose and files_indexed % 10 == 0:
                    print(f"  Indexed {files_indexed} files, {chunks_created} chunks...")

            except Exception as e:
                if verbose:
                    print(f"  Warning: Failed to index {file_path}: {e}")

        # Save metadata
        self.index_metadata = {
            "indexed_at": datetime.now().isoformat(),
            "project_root": str(self.project_root),
            "files_indexed": files_indexed,
            "chunks_created": chunks_created,
        }

        # Cache the index
        self._save_index()

        if verbose:
            print(f"\nIndexing complete:")
            print(f"  Files indexed: {files_indexed}")
            print(f"  Chunks created: {chunks_created}")
            print(f"  Cache saved to: {self.cache_dir}")

        return files_indexed, chunks_created

    def _save_index(self):
        """Save the index to cache."""
        index_file = self.cache_dir / "index.json"

        data = {
            "metadata": self.index_metadata,
            "chunks": [
                {
                    "file_path": chunk.file_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "chunk_type": chunk.chunk_type,
                    "name": chunk.name,
                    "content": chunk.content,
                }
                for chunk in self.code_chunks
            ],
        }

        with open(index_file, "w") as f:
            json.dump(data, f, indent=2)

    def _load_index(self) -> bool:
        """Load the index from cache. Returns True if successful."""
        index_file = self.cache_dir / "index.json"

        if not index_file.exists():
            return False

        try:
            with open(index_file, "r") as f:
                data = json.load(f)

            self.index_metadata = data["metadata"]
            self.code_chunks = [
                CodeChunk(
                    file_path=chunk["file_path"],
                    content=chunk["content"],
                    start_line=chunk["start_line"],
                    end_line=chunk["end_line"],
                    chunk_type=chunk["chunk_type"],
                    name=chunk.get("name"),
                )
                for chunk in data["chunks"]
            ]

            return True
        except Exception as e:
            print(f"Warning: Failed to load cache: {e}")
            return False

    def build_context(self, max_chunks: int = 50) -> str:
        """
        Build a context string from code chunks for prompt caching.

        Args:
            max_chunks: Maximum number of chunks to include

        Returns:
            Formatted context string
        """
        # Prioritize important files
        priority_patterns = [
            "strategies/",
            "backtesting/",
            "live/",
            "config/",
            "CLAUDE.md",
            "README.md",
        ]

        # Sort chunks by priority
        def chunk_priority(chunk: CodeChunk) -> int:
            for i, pattern in enumerate(priority_patterns):
                if pattern in chunk.file_path:
                    return i
            return len(priority_patterns)

        sorted_chunks = sorted(self.code_chunks, key=chunk_priority)[:max_chunks]

        # Build context
        context_parts = []
        context_parts.append("# CODEBASE CONTEXT\n")
        context_parts.append(f"Project: {self.project_root.name}\n")
        context_parts.append(f"Indexed: {self.index_metadata.get('indexed_at', 'unknown')}\n")
        context_parts.append(
            f"Total chunks: {len(self.code_chunks)} (showing top {len(sorted_chunks)})\n"
        )
        context_parts.append("\n---\n\n")

        for chunk in sorted_chunks:
            context_parts.append(f"## File: {chunk.file_path}\n")
            if chunk.name:
                context_parts.append(f"### {chunk.chunk_type}: {chunk.name}\n")
            context_parts.append(f"Lines {chunk.start_line}-{chunk.end_line}\n\n")
            context_parts.append("```\n")
            context_parts.append(chunk.content)
            context_parts.append("\n```\n\n")
            context_parts.append("---\n\n")

        return "".join(context_parts)

    def query(
        self,
        query: str,
        use_cache: bool = True,
        model: str = "claude-sonnet-4-5-20250929",
        verbose: bool = True,
    ) -> str:
        """
        Query the codebase using Claude API with prompt caching.

        Args:
            query: The query/instruction to execute
            use_cache: Whether to use prompt caching (90% cost reduction)
            model: Claude model to use
            verbose: Whether to print progress

        Returns:
            Claude's response
        """
        # Ensure index is loaded
        if not self.code_chunks:
            if verbose:
                print("Loading index...")
            if not self._load_index():
                if verbose:
                    print("No index found. Indexing codebase...")
                self.index_codebase(verbose=verbose)

        # Build context
        if verbose:
            print("Building context...")
        context = self.build_context()

        # Prepare messages
        if use_cache:
            # Use prompt caching for 90% cost reduction
            # The context is marked as cacheable
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": context,
                            "cache_control": {"type": "ephemeral"},
                        },
                        {
                            "type": "text",
                            "text": f"\n\n# QUERY\n\n{query}",
                        },
                    ],
                }
            ]
        else:
            messages = [{"role": "user", "content": f"{context}\n\n# QUERY\n\n{query}"}]

        # Call Claude API
        if verbose:
            print(f"Querying Claude ({model})...")

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=4096,
                messages=messages,
                system="You are an expert software engineer helping with code analysis and modification. "
                "Provide clear, actionable responses. When suggesting code changes, show the "
                "complete modified code with line numbers.",
            )

            # Extract response
            result = response.content[0].text

            # Print usage stats
            if verbose:
                usage = response.usage
                print(f"\nToken usage:")
                print(f"  Input tokens: {usage.input_tokens}")
                if hasattr(usage, "cache_creation_input_tokens"):
                    print(f"  Cache creation: {usage.cache_creation_input_tokens}")
                if hasattr(usage, "cache_read_input_tokens"):
                    print(f"  Cache read: {usage.cache_read_input_tokens}")
                print(f"  Output tokens: {usage.output_tokens}")

                # Calculate cost savings
                if use_cache and hasattr(usage, "cache_read_input_tokens"):
                    cache_read = usage.cache_read_input_tokens
                    normal_input = usage.input_tokens
                    if cache_read > 0:
                        savings_pct = (cache_read / (cache_read + normal_input)) * 100
                        print(f"  Cache savings: ~{savings_pct:.1f}%")

            return result

        except Exception as e:
            print(f"Error querying Claude: {e}")
            raise


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Claude Code RAG - Query and modify your codebase with AI assistance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Query the codebase
  python tools/claude_rag.py --query "Show me the current spread entry logic"

  # Request code modifications
  python tools/claude_rag.py --query "Add logging to all entry decisions"

  # Rebuild the index
  python tools/claude_rag.py --index

  # Query with custom settings
  python tools/claude_rag.py --query "Find all TODO comments" --no-cache
        """,
    )

    parser.add_argument(
        "--query",
        type=str,
        help="Query or instruction to execute on the codebase",
    )

    parser.add_argument(
        "--index",
        action="store_true",
        help="Rebuild the codebase index",
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable prompt caching (not recommended)",
    )

    parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="Project root directory (default: current directory)",
    )

    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-5-20250929",
        help="Claude model to use (default: claude-sonnet-4-5-20250929)",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress messages",
    )

    args = parser.parse_args()

    # Determine project root
    project_root = Path(args.project_root).resolve()

    if not project_root.exists():
        print(f"Error: Project root does not exist: {project_root}")
        sys.exit(1)

    # Initialize RAG system
    try:
        rag = ClaudeCodeRAG(project_root=project_root)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Handle --index
    if args.index:
        rag.index_codebase(verbose=not args.quiet)
        return

    # Handle --query
    if args.query:
        result = rag.query(
            query=args.query,
            use_cache=not args.no_cache,
            model=args.model,
            verbose=not args.quiet,
        )

        print("\n" + "=" * 80)
        print("RESPONSE")
        print("=" * 80 + "\n")
        print(result)
        return

    # No action specified
    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
