

## Brief overview
  - Global rule governing how new files and folders should be created during development tasks.
  - Applies to all projects and all tasks, regardless of scope.

## File and folder creation
  - Always use the command line (e.g., `mkdir -p`, `touch`, `cat >`, `echo`) to create any new file or folder.
  - Do NOT depend on MCP tools for creating files or directories.
  - Prefer shell commands over any MCP-based file creation utilities.

## Rationale
  - Keeps file system operations explicit, predictable, and reproducible.
  - Avoids hidden side effects or inconsistencies introduced by MCP tool abstractions.