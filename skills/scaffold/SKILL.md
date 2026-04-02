---
name: scaffold
description: Generate complete runnable projects from a description — API, CLI, MCP server, full-stack app
level: 3
triggers:
  - scaffold
  - create project
  - new project
  - bootstrap
user-invocable: true
pipeline:
  - scaffolder (generate) → executor (customize) → verifier (it runs)
---

# Scaffold Skill

## Purpose
Go from "I need a [thing]" to a running project in under 2 minutes. Not boilerplate — a real, runnable starting point with tests, types, and sensible defaults.

## When to Use
- "Create a new API for lead management"
- "Scaffold an MCP server that exposes our database"
- "Bootstrap a React dashboard"
- "New Python CLI tool for data processing"
- Starting any new project from scratch

## Execution Policy
- **Speed over perfection** — Get something running fast, refine later
- **Always verify** — `npm start` / `python main.py` must work before reporting done
- **Match existing stack** — If scaffolding inside an existing repo, match its conventions

## Workflow

### Phase 1: Requirements
Parse the user's description to determine:
- **Type**: API, CLI, MCP server, frontend, full-stack, library, script
- **Stack**: Python, Node/TS, Rust, Go (or auto-detect from existing repo)
- **Features**: Auth, database, file upload, WebSocket, etc.
- **Name**: Project name (from description or ask)

### Phase 2: Generate
Spawn `scaffolder` agent with requirements:
1. Create directory structure
2. Write all files with functional content
3. Set up package management
4. Configure dev tools (lint, format, types)
5. Create .gitignore and .env.example
6. Write at least one working test

### Phase 3: Customize (if needed)
If user specified specific features (auth, database, etc.):
- Spawn `executor` to implement the features on top of the scaffold
- Spawn `db-engineer` if database is needed

### Phase 4: Verify
1. Install dependencies
2. Run the project — it must start without errors
3. Run tests — they must pass
4. Report: what was created, how to run it, what to build next

## Templates Available
| Type | Command | Stack |
|------|---------|-------|
| REST API | `/scaffold api` | FastAPI / Hono |
| MCP Server | `/scaffold mcp-server` | Python / TypeScript |
| CLI Tool | `/scaffold cli` | Python (Typer) / Node |
| React App | `/scaffold frontend` | React + Vite + TS |
| Full Stack | `/scaffold fullstack` | FastAPI + React |
| Library | `/scaffold lib` | Matches repo language |
| Script | `/scaffold script` | Python / Bash |
