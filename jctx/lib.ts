import { Database } from "bun:sqlite";
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { basename, extname, join, resolve } from "node:path";
import { homedir } from "node:os";

export const JCTX_NAME = "jctx — Jailbreak Context Overlay";
export const DEFAULT_HOME = join(homedir(), ".jailbreak", "jctx");
export const DATA_DIR = process.env.JCTX_HOME ? resolve(process.env.JCTX_HOME) : DEFAULT_HOME;
export const DB_PATH = join(DATA_DIR, "jctx.sqlite");
export const ARTIFACT_DIR = join(DATA_DIR, "artifacts");
export const SPECULATION_DIR = join(DATA_DIR, "speculations");
export const SKILL_DIR = join(DATA_DIR, "skills");

export type ArtifactKind = "file" | "url" | "text" | "command" | "system" | "agent-os" | "speculation";

export function ensureStore() {
  mkdirSync(DATA_DIR, { recursive: true });
  mkdirSync(ARTIFACT_DIR, { recursive: true });
  mkdirSync(SPECULATION_DIR, { recursive: true });
  mkdirSync(SKILL_DIR, { recursive: true });
  const db = new Database(DB_PATH);
  db.exec(`
    PRAGMA journal_mode = WAL;
    CREATE TABLE IF NOT EXISTS artifacts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      kind TEXT NOT NULL,
      title TEXT NOT NULL,
      source TEXT NOT NULL,
      content_path TEXT,
      summary TEXT NOT NULL,
      tags TEXT NOT NULL DEFAULT '',
      byte_count INTEGER NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_type TEXT NOT NULL,
      detail TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS blackboard_tasks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      agent TEXT NOT NULL,
      task TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      evidence TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS verifications (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      request TEXT NOT NULL,
      checklist TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'draft',
      evidence TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS skills (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      trigger TEXT NOT NULL,
      body TEXT NOT NULL,
      path TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS immune_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      severity TEXT NOT NULL,
      rule TEXT NOT NULL,
      detail TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS speculations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      slug TEXT NOT NULL UNIQUE,
      prompt TEXT NOT NULL,
      base_branch TEXT NOT NULL,
      repo_path TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'planned',
      variants TEXT NOT NULL,
      summary TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS artifacts_fts USING fts5(
      title,
      source,
      summary,
      content,
      tags,
      content=''
    );
  `);
  return db;
}

export function summarize(content: string, max = 900) {
  const cleaned = content
    .replace(/\r/g, "")
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line, index, lines) => line.trim() || lines[index - 1]?.trim())
    .join("\n")
    .trim();
  if (cleaned.length <= max) return cleaned;
  const head = cleaned.slice(0, Math.floor(max * 0.65)).trimEnd();
  const tail = cleaned.slice(-Math.floor(max * 0.25)).trimStart();
  return `${head}\n\n… [${cleaned.length - head.length - tail.length} chars omitted; full text in jctx show]\n\n${tail}`;
}

export function slugify(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-|-$/g, "").slice(0, 80) || "item";
}

function artifactPath(id: number, title: string) {
  return join(ARTIFACT_DIR, `${String(id).padStart(6, "0")}-${slugify(title)}.txt`);
}

export function storeArtifact(db: Database, input: { kind: ArtifactKind; title: string; source: string; content: string; tags?: string }) {
  const summary = summarize(input.content);
  const result = db.query(`INSERT INTO artifacts (kind, title, source, summary, tags, byte_count) VALUES (?, ?, ?, ?, ?, ?)`).run(
    input.kind,
    input.title,
    input.source,
    summary,
    input.tags ?? "",
    Buffer.byteLength(input.content),
  );
  const id = Number(result.lastInsertRowid);
  const path = artifactPath(id, input.title);
  writeFileSync(path, input.content);
  db.query(`UPDATE artifacts SET content_path = ? WHERE id = ?`).run(path, id);
  db.query(`INSERT INTO artifacts_fts (rowid, title, source, summary, content, tags) VALUES (?, ?, ?, ?, ?, ?)`).run(
    id,
    input.title,
    input.source,
    summary,
    input.content,
    input.tags ?? "",
  );
  recordEvent(db, "artifact.indexed", `${input.kind}:${input.source}`);
  return { id, path, summary };
}

export function recordEvent(db: Database, eventType: string, detail: string) {
  db.query(`INSERT INTO events (event_type, detail) VALUES (?, ?)`).run(eventType, detail);
}

export function textExts() {
  return [".txt", ".md", ".json", ".jsonl", ".log", ".ts", ".tsx", ".js", ".jsx", ".py", ".sh", ".yaml", ".yml", ".toml"];
}

export function walkFiles(root: string, recursive: boolean, limit = 100, exts?: string[]) {
  const out: string[] = [];
  const visit = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (out.length >= limit) return;
      const full = join(dir, entry.name);
      if (entry.isDirectory()) {
        if (recursive && !entry.name.startsWith(".") && entry.name !== "node_modules") visit(full);
      } else if (entry.isFile()) {
        if (!exts || exts.includes(extname(entry.name).toLowerCase())) out.push(full);
      }
    }
  };
  visit(root);
  return out;
}

export function readSmallTextFile(path: string, maxBytes = 5 * 1024 * 1024) {
  const st = statSync(path);
  if (st.size > maxBytes) throw new Error(`File too large for direct indexing: ${path}`);
  return readFileSync(path, "utf8");
}

export function parseFlags(args: string[]) {
  const flags: Record<string, string | boolean> = {};
  const rest: string[] = [];
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === "--") {
      rest.push(...args.slice(i + 1));
      break;
    }
    if (arg.startsWith("--")) {
      const key = arg.slice(2);
      const next = args[i + 1];
      if (next && !next.startsWith("--")) {
        flags[key] = next;
        i++;
      } else {
        flags[key] = true;
      }
    } else {
      rest.push(arg);
    }
  }
  return { flags, rest };
}

export function requireRepo(path: string) {
  const gitDir = join(path, ".git");
  if (!existsSync(gitDir)) throw new Error(`Not a git repository: ${path}`);
}

export function nowSlug() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}
