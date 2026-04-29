#!/usr/bin/env bun
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { ensureStore, nowSlug, parseFlags, recordEvent, requireRepo, slugify, SPECULATION_DIR, storeArtifact, summarize } from "./lib.ts";

const VARIANTS = [
  { name: "conservative", brief: "Minimal patch. Preserve behavior. Touch the fewest files." },
  { name: "test-first", brief: "Start with reproduction or acceptance tests, then smallest implementation." },
  { name: "architectural", brief: "Clean design pass. Improve structure while staying within requested scope." },
];

function usage(exitCode = 0): never {
  console.log(`speculate — isolated variant worktree planner\n\nUsage:\n  speculate start "<task>" [--repo <path>] [--variants conservative,test-first,architectural] [--execute <command-template>]\n  speculate list\n  speculate show <slug>\n  speculate cleanup <slug> --yes\n\nCommand template variables:\n  {prompt}   task prompt\n  {variant}  variant name\n  {brief}    variant strategy brief\n  {path}     worktree path\n\nDefault mode is safe: create worktrees + instructions only. Add --execute to run a command per variant.\n`);
  process.exit(exitCode);
}

function git(repo: string, args: string[], okStatus = [0]) {
  const result = spawnSync("git", args, { cwd: repo, encoding: "utf8", maxBuffer: 20 * 1024 * 1024 });
  if (!okStatus.includes(result.status ?? 1)) {
    throw new Error(`git ${args.join(" ")} failed\n${result.stdout}\n${result.stderr}`);
  }
  return result.stdout.trim();
}

function shell(command: string, cwd: string) {
  return spawnSync(command, { cwd, shell: true, encoding: "utf8", maxBuffer: 50 * 1024 * 1024 });
}

function currentBranch(repo: string) {
  return git(repo, ["branch", "--show-current"]) || "HEAD";
}

function selectedVariants(value?: string | boolean) {
  if (!value || value === true) return VARIANTS;
  const wanted = String(value).split(",").map((x) => x.trim()).filter(Boolean);
  return wanted.map((name) => {
    const found = VARIANTS.find((v) => v.name === name);
    return found ?? { name: slugify(name), brief: `Explore ${name} approach.` };
  });
}

function start(args: string[]) {
  const { flags, rest } = parseFlags(args);
  const prompt = rest.join(" ").trim();
  if (!prompt) usage(1);
  const repo = resolve(String(flags.repo ?? process.cwd()));
  requireRepo(repo);
  const db = ensureStore();
  const branch = currentBranch(repo);
  const slug = `${nowSlug()}-${slugify(prompt).slice(0, 48)}`;
  const root = join(SPECULATION_DIR, slug);
  mkdirSync(root, { recursive: true });
  const variants = selectedVariants(flags.variants);
  const records: any[] = [];
  for (const variant of variants) {
    const worktreePath = join(root, variant.name);
    const variantBranch = `spec/${slugify(prompt).slice(0, 32)}-${variant.name}-${Date.now().toString(36)}`;
    git(repo, ["worktree", "add", "-b", variantBranch, worktreePath, branch]);
    const instructions = [
      `# Speculation Variant: ${variant.name}`,
      "",
      `Task: ${prompt}`,
      `Strategy: ${variant.brief}`,
      "",
      "Rules:",
      "- Work only inside this worktree.",
      "- Keep changes scoped to this variant.",
      "- Record verification evidence before recommending merge.",
      "- Do not push from variant worktrees unless explicitly asked.",
      "",
    ].join("\n");
    writeFileSync(join(worktreePath, "JCTX_SPECULATION.md"), instructions);
    let executeResult = null;
    if (flags.execute) {
      const command = String(flags.execute)
        .replaceAll("{prompt}", prompt.replaceAll('"', '\\"'))
        .replaceAll("{variant}", variant.name)
        .replaceAll("{brief}", variant.brief.replaceAll('"', '\\"'))
        .replaceAll("{path}", worktreePath.replaceAll('"', '\\"'));
      const result = shell(command, worktreePath);
      executeResult = {
        command,
        status: result.status,
        stdout: result.stdout,
        stderr: result.stderr,
      };
      storeArtifact(db, {
        kind: "speculation",
        title: `speculate ${slug}/${variant.name} execution`,
        source: worktreePath,
        content: JSON.stringify(executeResult, null, 2),
        tags: `speculate,${variant.name}`,
      });
    }
    records.push({ ...variant, branch: variantBranch, path: worktreePath, executeResult });
  }
  const content = JSON.stringify({ slug, prompt, repo, baseBranch: branch, variants: records }, null, 2);
  storeArtifact(db, { kind: "speculation", title: `speculation ${slug}`, source: root, content, tags: "speculate,worktree" });
  db.query(`INSERT INTO speculations (slug, prompt, base_branch, repo_path, status, variants, summary) VALUES (?, ?, ?, ?, ?, ?, ?)`).run(
    slug,
    prompt,
    branch,
    repo,
    flags.execute ? "executed" : "planned",
    JSON.stringify(records),
    summarize(content, 500),
  );
  recordEvent(db, "speculation.started", slug);
  console.log(`Speculation created: ${slug}`);
  for (const record of records) console.log(`- ${record.name}: ${record.path} (${record.branch})`);
}

function list() {
  const db = ensureStore();
  const rows = db.query(`SELECT slug, prompt, status, created_at FROM speculations ORDER BY id DESC LIMIT 20`).all() as any[];
  if (!rows.length) {
    console.log("No speculations recorded.");
    return;
  }
  for (const row of rows) console.log(`${row.slug}\t${row.status}\t${row.created_at}\t${row.prompt}`);
}

function show(args: string[]) {
  const slug = args[0];
  if (!slug) usage(1);
  const db = ensureStore();
  const row = db.query(`SELECT * FROM speculations WHERE slug = ?`).get(slug) as any;
  if (!row) throw new Error(`No speculation: ${slug}`);
  console.log(`slug: ${row.slug}`);
  console.log(`status: ${row.status}`);
  console.log(`repo: ${row.repo_path}`);
  console.log(`base: ${row.base_branch}`);
  console.log(`prompt: ${row.prompt}`);
  console.log("variants:");
  for (const variant of JSON.parse(row.variants)) console.log(`- ${variant.name}: ${variant.path} (${variant.branch})`);
}

function cleanup(args: string[]) {
  const { flags, rest } = parseFlags(args);
  const slug = rest[0];
  if (!slug || !flags.yes) usage(1);
  const db = ensureStore();
  const row = db.query(`SELECT * FROM speculations WHERE slug = ?`).get(slug) as any;
  if (!row) throw new Error(`No speculation: ${slug}`);
  const variants = JSON.parse(row.variants);
  for (const variant of variants) {
    if (existsSync(variant.path)) {
      const result = spawnSync("git", ["worktree", "remove", variant.path, "--force"], { cwd: row.repo_path, encoding: "utf8" });
      if (result.status !== 0) console.error(result.stderr || result.stdout);
    }
  }
  db.query(`UPDATE speculations SET status = 'cleaned', updated_at = CURRENT_TIMESTAMP WHERE slug = ?`).run(slug);
  recordEvent(db, "speculation.cleaned", slug);
  console.log(`Cleaned speculation worktrees: ${slug}`);
}

try {
  const [cmd, ...args] = Bun.argv.slice(2);
  switch (cmd) {
    case "start":
      start(args);
      break;
    case "list":
      list();
      break;
    case "show":
      show(args);
      break;
    case "cleanup":
      cleanup(args);
      break;
    case undefined:
    case "help":
    case "--help":
    case "-h":
      usage(0);
    default:
      usage(1);
  }
} catch (error) {
  console.error(`speculate error: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
}
