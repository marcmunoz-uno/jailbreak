#!/usr/bin/env bun
import { Database } from "bun:sqlite";
import { existsSync, mkdirSync, readFileSync, statSync, readdirSync } from "node:fs";
import { basename, dirname, extname, join, resolve } from "node:path";
import { homedir } from "node:os";
import { spawnSync } from "node:child_process";

const NAME = "jctx — Jailbreak Context Overlay";
const DESCRIPTION = "Additive context cold-storage, search, and Marc-stack indexing for Jailbreak without changing foundation config.";
const DEFAULT_HOME = join(homedir(), ".jailbreak", "jctx");
const DATA_DIR = process.env.JCTX_HOME ? resolve(process.env.JCTX_HOME) : DEFAULT_HOME;
const DB_PATH = join(DATA_DIR, "jctx.sqlite");
const ARTIFACT_DIR = join(DATA_DIR, "artifacts");
const MAX_PRINT_CHARS = Number(process.env.JCTX_MAX_PRINT_CHARS ?? 4000);

type ArtifactKind = "file" | "url" | "text" | "command" | "system";

type SourceSpec = {
  label: string;
  path: string;
  recursive?: boolean;
  limit?: number;
  exts?: string[];
};

function ensureStore() {
  mkdirSync(DATA_DIR, { recursive: true });
  mkdirSync(ARTIFACT_DIR, { recursive: true });
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

function usage(exitCode = 0): never {
  const text = `${NAME}\n${DESCRIPTION}\n\nUsage:\n  jctx doctor\n  jctx index <file|dir|url> [--title <title>] [--tags <tags>] [--recursive]\n  jctx add --title <title> [--tags <tags>] < text\n  jctx run -- <command> [args...]\n  jctx search <query> [--limit <n>]\n  jctx show <id>\n  jctx stats\n  jctx collect marc [--limit <n>]\n  jctx purge --yes\n\nStorage:\n  ${DB_PATH}\n`;
  console.log(text);
  process.exit(exitCode);
}

function parseFlags(args: string[]) {
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

function summarize(content: string, max = 900) {
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

function artifactPath(id: number, title: string) {
  const safe = title.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-|-$/g, "").slice(0, 80) || "artifact";
  return join(ARTIFACT_DIR, `${String(id).padStart(6, "0")}-${safe}.txt`);
}

function storeArtifact(db: Database, input: { kind: ArtifactKind; title: string; source: string; content: string; tags?: string }) {
  const summary = summarize(input.content);
  const insert = db.query(`INSERT INTO artifacts (kind, title, source, summary, tags, byte_count) VALUES (?, ?, ?, ?, ?, ?)`);
  const result = insert.run(input.kind, input.title, input.source, summary, input.tags ?? "", Buffer.byteLength(input.content));
  const id = Number(result.lastInsertRowid);
  const path = artifactPath(id, input.title);
  Bun.write(path, input.content);
  db.query(`UPDATE artifacts SET content_path = ? WHERE id = ?`).run(path, id);
  db.query(`INSERT INTO artifacts_fts (rowid, title, source, summary, content, tags) VALUES (?, ?, ?, ?, ?, ?)`).run(
    id,
    input.title,
    input.source,
    summary,
    input.content,
    input.tags ?? "",
  );
  db.query(`INSERT INTO events (event_type, detail) VALUES (?, ?)`).run("artifact.indexed", `${input.kind}:${input.source}`);
  return { id, path, summary };
}

function isUrl(value: string) {
  return /^https?:\/\//i.test(value);
}

async function readUrl(url: string) {
  const res = await fetch(url, { headers: { "user-agent": "jctx/0.1" } });
  if (!res.ok) throw new Error(`Fetch failed ${res.status} ${res.statusText}: ${url}`);
  return await res.text();
}

function walkFiles(root: string, recursive: boolean, limit = 100, exts?: string[]) {
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

async function cmdIndex(args: string[]) {
  const { flags, rest } = parseFlags(args);
  const target = rest[0];
  if (!target) usage(1);
  const db = ensureStore();
  const tags = String(flags.tags ?? "manual");
  if (isUrl(target)) {
    const content = await readUrl(target);
    const title = String(flags.title ?? target);
    const stored = storeArtifact(db, { kind: "url", title, source: target, content, tags });
    printStored(stored.id, title, stored.summary);
    return;
  }
  const abs = resolve(target);
  if (!existsSync(abs)) throw new Error(`Not found: ${abs}`);
  const st = statSync(abs);
  if (st.isDirectory()) {
    const files = walkFiles(abs, Boolean(flags.recursive), Number(flags.limit ?? 100), textExts());
    for (const file of files) {
      const content = readFileSync(file, "utf8");
      storeArtifact(db, { kind: "file", title: String(flags.title ?? basename(file)), source: file, content, tags });
    }
    console.log(`Indexed ${files.length} files from ${abs}`);
    return;
  }
  const content = readFileSync(abs, "utf8");
  const title = String(flags.title ?? basename(abs));
  const stored = storeArtifact(db, { kind: "file", title, source: abs, content, tags });
  printStored(stored.id, title, stored.summary);
}

async function cmdAdd(args: string[]) {
  const { flags } = parseFlags(args);
  const title = String(flags.title ?? "stdin");
  const tags = String(flags.tags ?? "manual,stdin");
  const content = await new Response(Bun.stdin.stream()).text();
  if (!content.trim()) throw new Error("No stdin content provided.");
  const db = ensureStore();
  const stored = storeArtifact(db, { kind: "text", title, source: "stdin", content, tags });
  printStored(stored.id, title, stored.summary);
}

function cmdRun(args: string[]) {
  const { flags, rest } = parseFlags(args);
  const command = rest[0];
  if (!command) usage(1);
  const started = Date.now();
  const result = spawnSync(command, rest.slice(1), {
    cwd: flags.cwd ? String(flags.cwd) : process.cwd(),
    encoding: "utf8",
    maxBuffer: 50 * 1024 * 1024,
    shell: false,
  });
  const elapsed = Date.now() - started;
  const content = [
    `$ ${rest.map(shellQuote).join(" ")}`,
    `exit_code=${result.status ?? "null"} elapsed_ms=${elapsed}`,
    result.stdout ? `\n--- stdout ---\n${result.stdout}` : "",
    result.stderr ? `\n--- stderr ---\n${result.stderr}` : "",
    result.error ? `\n--- error ---\n${result.error.message}` : "",
  ].join("\n");
  const db = ensureStore();
  const title = String(flags.title ?? `command: ${rest.join(" ").slice(0, 80)}`);
  const stored = storeArtifact(db, { kind: "command", title, source: rest.join(" "), content, tags: String(flags.tags ?? "command") });
  console.log(`jctx stored command output #${stored.id} (${Buffer.byteLength(content)} bytes)`);
  console.log(summarize(content, MAX_PRINT_CHARS));
  process.exit(result.status ?? 1);
}

function shellQuote(value: string) {
  return /^[a-zA-Z0-9_./:=@+-]+$/.test(value) ? value : JSON.stringify(value);
}

function cmdSearch(args: string[]) {
  const { flags, rest } = parseFlags(args);
  const query = rest.join(" ").trim();
  if (!query) usage(1);
  const limit = Number(flags.limit ?? 8);
  const db = ensureStore();
  const rows = db.query(`
    SELECT a.id, a.kind, a.title, a.source, a.summary, a.tags, a.byte_count, a.created_at, bm25(artifacts_fts) AS rank
    FROM artifacts_fts
    JOIN artifacts a ON a.id = artifacts_fts.rowid
    WHERE artifacts_fts MATCH ?
    ORDER BY rank
    LIMIT ?
  `).all(query, limit) as any[];
  if (!rows.length) {
    console.log("No jctx matches.");
    return;
  }
  for (const row of rows) {
    console.log(`#${row.id} [${row.kind}] ${row.title}`);
    console.log(`source: ${row.source}`);
    console.log(`tags: ${row.tags || "-"} | bytes: ${row.byte_count} | ${row.created_at}`);
    console.log(summarize(row.summary, 500));
    console.log("---");
  }
}

function cmdShow(args: string[]) {
  const id = Number(args[0]);
  if (!id) usage(1);
  const db = ensureStore();
  const row = db.query(`SELECT * FROM artifacts WHERE id = ?`).get(id) as any;
  if (!row) throw new Error(`No artifact #${id}`);
  console.log(`#${row.id} [${row.kind}] ${row.title}`);
  console.log(`source: ${row.source}`);
  console.log(`tags: ${row.tags || "-"} | bytes: ${row.byte_count} | ${row.created_at}`);
  console.log("");
  const content = row.content_path && existsSync(row.content_path) ? readFileSync(row.content_path, "utf8") : row.summary;
  console.log(content);
}

function cmdStats() {
  const db = ensureStore();
  const total = db.query(`SELECT COUNT(*) AS n, COALESCE(SUM(byte_count), 0) AS bytes FROM artifacts`).get() as any;
  const byKind = db.query(`SELECT kind, COUNT(*) AS n, COALESCE(SUM(byte_count), 0) AS bytes FROM artifacts GROUP BY kind ORDER BY bytes DESC`).all() as any[];
  const recent = db.query(`SELECT id, kind, title, byte_count, created_at FROM artifacts ORDER BY id DESC LIMIT 5`).all() as any[];
  console.log(NAME);
  console.log(`db: ${DB_PATH}`);
  console.log(`artifacts: ${total.n} | raw bytes cold-stored: ${total.bytes}`);
  console.log("by kind:");
  for (const row of byKind) console.log(`  ${row.kind}: ${row.n} (${row.bytes} bytes)`);
  console.log("recent:");
  for (const row of recent) console.log(`  #${row.id} [${row.kind}] ${row.title} (${row.byte_count} bytes, ${row.created_at})`);
}

function cmdDoctor() {
  const db = ensureStore();
  const fts = db.query(`SELECT name FROM sqlite_master WHERE type='table' AND name='artifacts_fts'`).get();
  console.log(NAME);
  console.log(DESCRIPTION);
  console.log(`[x] data dir: ${DATA_DIR}`);
  console.log(`[x] db: ${DB_PATH}`);
  console.log(`[x] artifact dir: ${ARTIFACT_DIR}`);
  console.log(`${fts ? "[x]" : "[ ]"} sqlite fts5 table`);
  console.log(`[x] no core Jailbreak config changes required`);
}

async function cmdCollect(args: string[]) {
  const { flags, rest } = parseFlags(args);
  if (rest[0] !== "marc") usage(1);
  const limit = Number(flags.limit ?? 25);
  const db = ensureStore();
  const sources: SourceSpec[] = [
    { label: "fabric", path: join(homedir(), "fabric"), recursive: true, limit, exts: textExts() },
    { label: "jailbreak-session-artifacts", path: join(homedir(), ".jailbreak", "projects", "-Users-marcmunoz"), recursive: true, limit, exts: [".txt", ".md", ".json", ".log"] },
    { label: "openclaw-logs", path: join(homedir(), ".openclaw", "logs"), recursive: true, limit, exts: [".log", ".txt", ".json"] },
    { label: "obsidian-start", path: join(homedir(), "ObsidianVault", "START HERE.md"), limit: 1 },
    { label: "obsidian-openclaw-home", path: join(homedir(), "ObsidianVault", "Openclaw", "🤖 OpenClaw System Home.md"), limit: 1 },
  ];
  let count = 0;
  for (const source of sources) {
    count += indexSource(db, source);
  }
  count += indexSystemBrain(db);
  console.log(`Marc-stack collection complete: indexed ${count} artifacts.`);
}

function indexSource(db: Database, source: SourceSpec) {
  if (!existsSync(source.path)) return 0;
  const st = statSync(source.path);
  const files = st.isDirectory() ? walkFiles(source.path, Boolean(source.recursive), source.limit ?? 25, source.exts) : [source.path];
  let count = 0;
  for (const file of files) {
    try {
      const st = statSync(file);
      if (st.size > 5 * 1024 * 1024) continue;
      const content = readFileSync(file, "utf8");
      storeArtifact(db, {
        kind: "system",
        title: `${source.label}: ${basename(file)}`,
        source: file,
        content,
        tags: `marc-stack,${source.label}`,
      });
      count++;
    } catch {
      // Ignore unreadable binary/rotating files; jctx is opportunistic cold storage.
    }
  }
  return count;
}

function indexSystemBrain(db: Database) {
  const systemBrainDb = join(homedir(), ".openclaw", "data", "system_brain.db");
  if (!existsSync(systemBrainDb)) return 0;
  try {
    const source = new Database(systemBrainDb, { readonly: true });
    const tables = source.query(`SELECT name FROM sqlite_master WHERE type='table' ORDER BY name`).all() as any[];
    const parts = [`system_brain.db tables: ${tables.map((row) => row.name).join(", ")}`];
    for (const table of tables.slice(0, 12)) {
      const name = String(table.name);
      if (!/^[a-zA-Z0-9_]+$/.test(name)) continue;
      const rows = source.query(`SELECT * FROM ${name} ORDER BY rowid DESC LIMIT 10`).all() as any[];
      parts.push(`\n## ${name}\n${JSON.stringify(rows, null, 2)}`);
    }
    storeArtifact(db, {
      kind: "system",
      title: "system-brain snapshot",
      source: systemBrainDb,
      content: parts.join("\n"),
      tags: "marc-stack,system-brain,openclaw",
    });
    return 1;
  } catch (error) {
    storeArtifact(db, {
      kind: "system",
      title: "system-brain snapshot error",
      source: systemBrainDb,
      content: error instanceof Error ? error.stack ?? error.message : String(error),
      tags: "marc-stack,system-brain,error",
    });
    return 1;
  }
}

function textExts() {
  return [".txt", ".md", ".json", ".jsonl", ".log", ".ts", ".tsx", ".js", ".jsx", ".py", ".sh", ".yaml", ".yml", ".toml"];
}

function cmdPurge(args: string[]) {
  if (!args.includes("--yes")) throw new Error("Refusing to purge without --yes");
  const db = ensureStore();
  db.exec(`DELETE FROM artifacts; DELETE FROM artifacts_fts; DELETE FROM events; VACUUM;`);
  console.log("Purged jctx index. Artifact files remain on disk for manual inspection:");
  console.log(ARTIFACT_DIR);
}

function printStored(id: number, title: string, summary: string) {
  console.log(`jctx stored #${id}: ${title}`);
  console.log(summary.length > MAX_PRINT_CHARS ? summarize(summary, MAX_PRINT_CHARS) : summary);
}

async function main() {
  const [cmd, ...args] = Bun.argv.slice(2);
  try {
    switch (cmd) {
      case undefined:
      case "help":
      case "--help":
      case "-h":
        usage(0);
      case "doctor":
        cmdDoctor();
        break;
      case "index":
        await cmdIndex(args);
        break;
      case "add":
        await cmdAdd(args);
        break;
      case "run":
        cmdRun(args);
        break;
      case "search":
        cmdSearch(args);
        break;
      case "show":
        cmdShow(args);
        break;
      case "stats":
        cmdStats();
        break;
      case "collect":
        await cmdCollect(args);
        break;
      case "purge":
        cmdPurge(args);
        break;
      default:
        usage(1);
    }
  } catch (error) {
    console.error(`jctx error: ${error instanceof Error ? error.message : String(error)}`);
    process.exit(1);
  }
}

await main();
