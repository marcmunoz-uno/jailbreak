#!/usr/bin/env bun
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, join, resolve } from "node:path";
import { ensureStore, parseFlags, recordEvent, SKILL_DIR, slugify, storeArtifact, summarize } from "./lib.ts";

function usage(exitCode = 0): never {
  console.log(`jailbreak-os — additive agent-OS overlays\n\nUsage:\n  jailbreak-os route "<intent>" [--bytes <n>] [--risk <low|medium|high>]\n  jailbreak-os board add --agent <name> --task <task> [--status <status>] [--evidence <text>]\n  jailbreak-os board list\n  jailbreak-os board update <id> --status <status> [--evidence <text>]\n  jailbreak-os verify create "<request>"\n  jailbreak-os verify list\n  jailbreak-os verify evidence <id> <text>\n  jailbreak-os skill mine --name <name> --trigger <pattern> --from <artifact-id|file>\n  jailbreak-os skill list\n  jailbreak-os immune scan [--recent <n>]\n\nThese are sidecar commands. They record state in JCTX and do not change harness config.\n`);
  process.exit(exitCode);
}

function route(args: string[]) {
  const { flags, rest } = parseFlags(args);
  const intent = rest.join(" ").trim();
  if (!intent) usage(1);
  const bytes = Number(flags.bytes ?? 0);
  const risk = String(flags.risk ?? inferRisk(intent));
  const lower = intent.toLowerCase();
  const recommendations: string[] = [];
  if (bytes > 20000 || /log|dump|snapshot|large|many files|repo-wide|crawl|scrape/.test(lower)) recommendations.push("Use jctx index/run/search to cold-store bulky output before exposing it to the model.");
  if (/unknown repo|map|explore|where is|how does/.test(lower)) recommendations.push("Spawn/read via Explore first; return cited file paths only.");
  if (/fix|implement|change|build|refactor/.test(lower)) recommendations.push("Create verification checklist before implementation.");
  if (/browser|website|portal|ui|screenshot/.test(lower)) recommendations.push("Use browser-harness; screenshot before and after meaningful actions.");
  if (risk === "high" || /delete|reset|force|drop|prod|secret|credential|push/.test(lower)) recommendations.push("Route through immune scan + verifier lane before irreversible action.");
  if (/repeat|recurring|every|cron|daemon/.test(lower)) recommendations.push("Prefer additive cron/sidecar wrapper; avoid core startup hook changes unless explicitly requested.");
  if (!recommendations.length) recommendations.push("Direct execution is fine; record non-obvious findings to JCTX if useful later.");
  const db = ensureStore();
  const body = JSON.stringify({ intent, bytes, risk, recommendations }, null, 2);
  storeArtifact(db, { kind: "agent-os", title: `route: ${intent.slice(0, 80)}`, source: "jailbreak-os route", content: body, tags: "router,agent-os" });
  console.log(body);
}

function inferRisk(intent: string) {
  return /delete|reset|force|drop|prod|credential|secret|token|push|deploy|payment|domain|dns/i.test(intent) ? "high" : "low";
}

function board(args: string[]) {
  const [cmd, ...restArgs] = args;
  const db = ensureStore();
  if (cmd === "add") {
    const { flags } = parseFlags(restArgs);
    const agent = String(flags.agent ?? "unassigned");
    const task = String(flags.task ?? "").trim();
    if (!task) usage(1);
    const status = String(flags.status ?? "pending");
    const evidence = String(flags.evidence ?? "");
    const result = db.query(`INSERT INTO blackboard_tasks (agent, task, status, evidence) VALUES (?, ?, ?, ?)`).run(agent, task, status, evidence);
    recordEvent(db, "blackboard.task.added", `${result.lastInsertRowid}:${task}`);
    console.log(`Added board task #${result.lastInsertRowid}`);
    return;
  }
  if (cmd === "list") {
    const rows = db.query(`SELECT * FROM blackboard_tasks ORDER BY id DESC LIMIT 50`).all() as any[];
    if (!rows.length) return console.log("Board empty.");
    for (const row of rows) console.log(`#${row.id} [${row.status}] ${row.agent}: ${row.task}${row.evidence ? ` | ${summarize(row.evidence, 140)}` : ""}`);
    return;
  }
  if (cmd === "update") {
    const { flags, rest } = parseFlags(restArgs);
    const id = Number(rest[0]);
    if (!id || !flags.status) usage(1);
    const current = db.query(`SELECT evidence FROM blackboard_tasks WHERE id = ?`).get(id) as any;
    if (!current) throw new Error(`No board task #${id}`);
    const evidence = flags.evidence ? `${current.evidence}\n${String(flags.evidence)}`.trim() : current.evidence;
    db.query(`UPDATE blackboard_tasks SET status = ?, evidence = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?`).run(String(flags.status), evidence, id);
    recordEvent(db, "blackboard.task.updated", `${id}:${flags.status}`);
    console.log(`Updated board task #${id}`);
    return;
  }
  usage(1);
}

function verify(args: string[]) {
  const [cmd, ...restArgs] = args;
  const db = ensureStore();
  if (cmd === "create") {
    const request = restArgs.join(" ").trim();
    if (!request) usage(1);
    const checklist = makeChecklist(request);
    const result = db.query(`INSERT INTO verifications (request, checklist) VALUES (?, ?)`).run(request, checklist);
    storeArtifact(db, { kind: "agent-os", title: `verification checklist #${result.lastInsertRowid}`, source: "jailbreak-os verify", content: checklist, tags: "verify,agent-os" });
    console.log(`#${result.lastInsertRowid}\n${checklist}`);
    return;
  }
  if (cmd === "list") {
    const rows = db.query(`SELECT id, request, status, evidence, created_at FROM verifications ORDER BY id DESC LIMIT 30`).all() as any[];
    if (!rows.length) return console.log("No verification checklists.");
    for (const row of rows) console.log(`#${row.id} [${row.status}] ${row.request}${row.evidence ? ` | evidence: ${summarize(row.evidence, 120)}` : ""}`);
    return;
  }
  if (cmd === "evidence") {
    const id = Number(restArgs[0]);
    const text = restArgs.slice(1).join(" ").trim();
    if (!id || !text) usage(1);
    const row = db.query(`SELECT evidence FROM verifications WHERE id = ?`).get(id) as any;
    if (!row) throw new Error(`No verification #${id}`);
    const evidence = `${row.evidence}\n- ${text}`.trim();
    db.query(`UPDATE verifications SET status = 'evidence-added', evidence = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?`).run(evidence, id);
    recordEvent(db, "verification.evidence", `${id}:${text}`);
    console.log(`Added evidence to verification #${id}`);
    return;
  }
  usage(1);
}

function makeChecklist(request: string) {
  const lower = request.toLowerCase();
  const items = [
    `Request: ${request}`,
    "",
    "Acceptance checklist:",
    "- Define expected behavior in one sentence.",
    "- Capture current failure or baseline state.",
    "- Make the smallest scoped change that satisfies the request.",
    "- Run a focused functional check.",
    "- Record exact command/output or artifact ID as evidence.",
  ];
  if (/test|bug|fix|regression/.test(lower)) items.push("- Add or run a regression check covering the failure mode.");
  if (/browser|ui|visual|website/.test(lower)) items.push("- Capture before/after screenshot or page state evidence.");
  if (/security|secret|auth|permission/.test(lower)) items.push("- Run security/risk review before final claim.");
  if (/push|deploy|release|production/.test(lower)) items.push("- Verify remote/shared-state impact and final status after action.");
  return items.join("\n");
}

function skill(args: string[]) {
  const [cmd, ...restArgs] = args;
  const db = ensureStore();
  if (cmd === "mine") {
    const { flags } = parseFlags(restArgs);
    const name = String(flags.name ?? "").trim();
    const trigger = String(flags.trigger ?? "").trim();
    const from = String(flags.from ?? "").trim();
    if (!name || !trigger || !from) usage(1);
    let sourceText = "";
    let source = from;
    if (/^\d+$/.test(from)) {
      const row = db.query(`SELECT content_path, summary FROM artifacts WHERE id = ?`).get(Number(from)) as any;
      if (!row) throw new Error(`No artifact #${from}`);
      sourceText = row.content_path && existsSync(row.content_path) ? readFileSync(row.content_path, "utf8") : row.summary;
      source = `artifact:${from}`;
    } else {
      const file = resolve(from);
      sourceText = readFileSync(file, "utf8");
      source = file;
    }
    const body = makeSkill(name, trigger, source, sourceText);
    mkdirSync(SKILL_DIR, { recursive: true });
    const path = join(SKILL_DIR, `${slugify(name)}.md`);
    writeFileSync(path, body);
    const result = db.query(`INSERT INTO skills (name, trigger, body, path) VALUES (?, ?, ?, ?)`).run(name, trigger, body, path);
    storeArtifact(db, { kind: "agent-os", title: `mined skill: ${name}`, source, content: body, tags: "skill-miner,agent-os" });
    console.log(`Mined skill #${result.lastInsertRowid}: ${path}`);
    return;
  }
  if (cmd === "list") {
    const rows = db.query(`SELECT id, name, trigger, path, created_at FROM skills ORDER BY id DESC LIMIT 30`).all() as any[];
    if (!rows.length) return console.log("No mined skills.");
    for (const row of rows) console.log(`#${row.id} ${row.name} | trigger: ${row.trigger} | ${row.path}`);
    return;
  }
  usage(1);
}

function makeSkill(name: string, trigger: string, source: string, sourceText: string) {
  return `# ${name}\n\nTrigger when: ${trigger}\n\nSource: ${source}\n\n## Reusable procedure\n\n${summarize(sourceText, 1800)}\n\n## Usage notes\n\n- Treat this as a mined draft skill. Review before promoting into a global skill registry.\n- Keep durable mechanics; remove one-off task narration before sharing.\n- Do not include secrets, cookies, tokens, or user-specific private state.\n`;
}

function immune(args: string[]) {
  const [cmd, ...restArgs] = args;
  if (cmd !== "scan") usage(1);
  const { flags } = parseFlags(restArgs);
  const db = ensureStore();
  const recent = Number(flags.recent ?? 100);
  const rows = db.query(`SELECT * FROM events ORDER BY id DESC LIMIT ?`).all(recent) as any[];
  const artifacts = db.query(`SELECT id, title, source, byte_count, tags FROM artifacts ORDER BY id DESC LIMIT ?`).all(recent) as any[];
  const findings: { severity: string; rule: string; detail: string }[] = [];
  const repeatedErrors = rows.filter((row) => /error|failed|denied/i.test(`${row.event_type} ${row.detail}`));
  if (repeatedErrors.length >= 3) findings.push({ severity: "medium", rule: "repeated-errors", detail: `${repeatedErrors.length} recent error-like events` });
  for (const artifact of artifacts) {
    if (artifact.byte_count > 100000) findings.push({ severity: "low", rule: "large-artifact", detail: `#${artifact.id} ${artifact.title} is ${artifact.byte_count} bytes; prefer search/show over dumping` });
    if (/secret|token|credential|key/i.test(`${artifact.title} ${artifact.source} ${artifact.tags}`)) findings.push({ severity: "high", rule: "possible-secret-context", detail: `#${artifact.id} metadata suggests sensitive material: ${artifact.title}` });
  }
  if (!findings.length) {
    console.log("Immune scan clean: no obvious recent agent-risk patterns.");
    return;
  }
  for (const finding of findings) {
    db.query(`INSERT INTO immune_events (severity, rule, detail) VALUES (?, ?, ?)`).run(finding.severity, finding.rule, finding.detail);
    console.log(`[${finding.severity}] ${finding.rule}: ${finding.detail}`);
  }
}

try {
  const [domain, ...args] = Bun.argv.slice(2);
  switch (domain) {
    case "route":
      route(args);
      break;
    case "board":
      board(args);
      break;
    case "verify":
      verify(args);
      break;
    case "skill":
      skill(args);
      break;
    case "immune":
      immune(args);
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
  console.error(`jailbreak-os error: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
}
