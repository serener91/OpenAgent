"""FastMCP server with file tools."""

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP(name="file_tools")


@mcp.tool()
async def read_file(path: str) -> dict[str, Any]:
    """Read the contents of a file.

    Args:
        path: Path to the file to read

    Returns:
        Dictionary with file contents or error
    """
    try:
        file_path = Path(path).resolve()
        if not file_path.exists():
            return {"error": f"File not found: {path}"}
        if not file_path.is_file():
            return {"error": f"Path is not a file: {path}"}

        contents = file_path.read_text()
        return {
            "success": True,
            "path": str(file_path),
            "contents": contents,
            "size": len(contents),
        }
    except PermissionError:
        return {"error": f"Permission denied: {path}"}
    except Exception as e:
        return {"error": f"Error reading file: {str(e)}"}


@mcp.tool()
async def list_directory(path: str) -> dict[str, Any]:
    """List contents of a directory.

    Args:
        path: Path to the directory to list

    Returns:
        Dictionary with directory contents or error
    """
    try:
        dir_path = Path(path).resolve()
        if not dir_path.exists():
            return {"error": f"Directory not found: {path}"}
        if not dir_path.is_dir():
            return {"error": f"Path is not a directory: {path}"}

        entries = []
        for entry in dir_path.iterdir():
            stat = entry.stat()
            entries.append(
                {
                    "name": entry.name,
                    "type": "directory" if entry.is_dir() else "file",
                    "size": stat.st_size if entry.is_file() else None,
                }
            )

        return {"success": True, "path": str(dir_path), "entries": entries}
    except PermissionError:
        return {"error": f"Permission denied: {path}"}
    except Exception as e:
        return {"error": f"Error listing directory: {str(e)}"}


def main():
    """Run the FastMCP server."""
    mcp.run()


if __name__ == "__main__":
    main()