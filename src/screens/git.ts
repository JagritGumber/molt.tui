// Git screen — full git dashboard with graph, branches, PRs, status
// Uses `git` and `gh` CLI for all operations

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, bg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawHR } from "../tui/components.ts";
import type { KeyEvent } from "../tui/input.ts";
import { execSync } from "child_process";

type View = "log" | "status" | "branches" | "prs" | "diff";

let view: View = "log";
let cwd = process.cwd();
let scrollOffset = 0;

// Cached data
let logLines: string[] = [];
let statusLines: string[] = [];
let branchLines: string[] = [];
let prLines: string[] = [];
let diffLines: string[] = [];
let currentBranch = "";
let repoName = "";

// All commands are hardcoded strings — no user input is interpolated
// execSync is safe here as this is a local TUI, not a web server
function run(cmd: string): string {
  try {
    return execSync(cmd, { cwd, encoding: "utf-8", timeout: 10000 }).trim();
  } catch {
    return "";
  }
}

function runAction(cmd: string): string {
  try {
    return execSync(cmd, { cwd, encoding: "utf-8", timeout: 15000 }).trim();
  } catch (err: any) {
    return err.stderr?.trim() || err.message?.slice(0, 80) || "command failed";
  }
}

function refresh() {
  currentBranch = run("git branch --show-current");
  repoName = run("git rev-parse --show-toplevel 2>/dev/null").split("/").pop() || "";

  if (view === "log") loadLog();
  else if (view === "status") loadStatus();
  else if (view === "branches") loadBranches();
  else if (view === "prs") loadPRs();
}

function loadLog() {
  const raw = run("git log --oneline --graph --decorate --all -50");
  logLines = raw ? raw.split("\n") : ["(no commits)"];
}

function loadStatus() {
  const raw = run("git status --short");
  statusLines = raw ? raw.split("\n") : ["(clean working tree)"];
}

function loadBranches() {
  const raw = run("git branch -a --sort=-committerdate --format='%(HEAD) %(refname:short) %(committerdate:relative) %(subject)'");
  branchLines = raw ? raw.split("\n").slice(0, 30) : ["(no branches)"];
}

function loadPRs() {
  const raw = run("gh pr list --limit 15 --json number,title,state,headRefName,author --template '{{range .}}#{{.number}} {{.state}} {{.headRefName}} {{.title}} ({{.author.login}}){{\"\\n\"}}{{end}}'");
  prLines = raw ? raw.split("\n").filter(Boolean) : ["(no PRs or gh not authenticated)"];
}

function loadDiff() {
  const raw = run("git diff --stat");
  const full = run("git diff --no-color");
  diffLines = raw ? [...raw.split("\n"), "", ...full.split("\n").slice(0, 200)] : ["(no changes)"];
}

// ── Graph coloring ──

function colorGraphLine(line: string): string {
  let result = "";
  let inGraph = true;

  for (let i = 0; i < line.length; i++) {
    const ch = line[i]!;
    if (inGraph && "*|/\\_ -".includes(ch)) {
      if (ch === "*") result += `${fg.brightYellow}${ch}${style.reset}`;
      else if (ch === "|") result += `${fg.brightCyan}${ch}${style.reset}`;
      else if (ch === "/" || ch === "\\") result += `${fg.brightMagenta}${ch}${style.reset}`;
      else result += ch;
    } else {
      inGraph = false;
      // Refs in parens
      if (ch === "(" && line.indexOf(")", i) > i) {
        const close = line.indexOf(")", i);
        result += `${fg.brightGreen}${style.bold}${line.slice(i, close + 1)}${style.reset}`;
        i = close;
        continue;
      }
      // Hash
      const hashMatch = line.slice(i).match(/^[a-f0-9]{7,9}/);
      if (hashMatch && i < 20) {
        result += `${fg.yellow}${hashMatch[0]}${style.reset}`;
        i += hashMatch[0].length - 1;
        continue;
      }
      result += `${fg.white}${ch}${style.reset}`;
    }
  }
  return result;
}

function colorStatusLine(line: string): string {
  const code = line.slice(0, 2);
  const file = line.slice(3);
  if (code.includes("M")) return `${fg.brightYellow}M${style.reset}  ${fg.white}${file}${style.reset}`;
  if (code.includes("A") || code.includes("?")) return `${fg.brightGreen}${code.trim()}${style.reset}  ${fg.white}${file}${style.reset}`;
  if (code.includes("D")) return `${fg.brightRed}D${style.reset}  ${fg.white}${file}${style.reset}`;
  if (code.includes("R")) return `${fg.brightMagenta}R${style.reset}  ${fg.white}${file}${style.reset}`;
  return `${fg.gray}${line}${style.reset}`;
}

function colorDiffLine(line: string): string {
  if (line.startsWith("+") && !line.startsWith("+++")) return `${fg.brightGreen}${line}${style.reset}`;
  if (line.startsWith("-") && !line.startsWith("---")) return `${fg.brightRed}${line}${style.reset}`;
  if (line.startsWith("@@")) return `${fg.brightCyan}${line}${style.reset}`;
  if (line.startsWith("diff ") || line.startsWith("index ")) return `${fg.brightMagenta}${style.bold}${line}${style.reset}`;
  return `${fg.gray}${line}${style.reset}`;
}

// ── Rendering ──

function renderTabs(row: number) {
  const tabs: { key: string; label: string; v: View }[] = [
    { key: "1", label: "Log", v: "log" },
    { key: "2", label: "Status", v: "status" },
    { key: "3", label: "Branches", v: "branches" },
    { key: "4", label: "PRs", v: "prs" },
    { key: "5", label: "Diff", v: "diff" },
  ];

  cursor.to(row, 3);
  write(tabs.map((t) => {
    const active = view === t.v;
    if (active) return `${bg.rgb(40, 40, 70)}${fg.brightCyan}${style.bold} ${t.key}:${t.label} ${style.reset}`;
    return `${fg.gray} ${t.key}:${t.label} ${style.reset}`;
  }).join("") + "\x1b[K");
}

function renderContent() {
  const { rows, cols } = getTermSize();
  const w = cols - 4;
  const maxLines = rows - 8;
  let lines: string[];
  let colorFn: (line: string) => string;

  switch (view) {
    case "log": lines = logLines; colorFn = colorGraphLine; break;
    case "status": lines = statusLines; colorFn = colorStatusLine; break;
    case "branches": lines = branchLines; colorFn = (l) => {
      if (l.startsWith("*")) return `${fg.brightCyan}${style.bold}${l}${style.reset}`;
      return `${fg.white}${l}${style.reset}`;
    }; break;
    case "prs": lines = prLines; colorFn = (l) => {
      if (l.includes("OPEN")) return l.replace("OPEN", `${fg.brightGreen}OPEN${style.reset}`);
      if (l.includes("MERGED")) return l.replace("MERGED", `${fg.brightMagenta}MERGED${style.reset}`);
      if (l.includes("CLOSED")) return l.replace("CLOSED", `${fg.brightRed}CLOSED${style.reset}`);
      return `${fg.white}${l}${style.reset}`;
    }; break;
    case "diff": lines = diffLines; colorFn = colorDiffLine; break;
    default: lines = []; colorFn = (l) => l;
  }

  // Clamp scroll
  const maxScroll = Math.max(0, lines.length - maxLines);
  if (scrollOffset > maxScroll) scrollOffset = maxScroll;

  for (let i = 0; i < maxLines; i++) {
    const idx = scrollOffset + i;
    cursor.to(6 + i, 3);
    if (idx >= lines.length) { write("\x1b[K"); continue; }
    const clean = lines[idx]!.replace(/[\n\r]/g, "").slice(0, w);
    write(`${colorFn(clean)}\x1b[K`);
  }

  // Info bar
  cursor.to(rows - 3, 3);
  const info = view === "status"
    ? `${fg.gray}f${fg.white} fetch  ${fg.gray}p${fg.white} pull  ${fg.gray}P${fg.white} push  ${fg.gray}s${fg.white} stage all  ${fg.gray}r${fg.white} refresh${style.reset}`
    : view === "branches"
    ? `${fg.gray}enter${fg.white} checkout  ${fg.gray}r${fg.white} refresh${style.reset}`
    : view === "prs"
    ? `${fg.gray}enter${fg.white} checkout PR  ${fg.gray}r${fg.white} refresh${style.reset}`
    : `${fg.gray}${scrollOffset + 1}-${Math.min(scrollOffset + maxLines, lines.length)} of ${lines.length}${style.reset}`;
  write(`${info}\x1b[K`);
}

// ── Screen ──

export const gitScreen: Screen = {
  name: "git",
  statusHint: "1-5 tabs • j/k scroll • r refresh • esc back",

  onEnter() {
    view = "log";
    scrollOffset = 0;
    refresh();
  },

  render() {
    const { cols } = getTermSize();

    cursor.to(3, 3);
    write(`${fg.brightCyan}${style.bold}Git${style.reset} ${fg.gray}${repoName}${style.reset} ${fg.brightGreen}${currentBranch}${style.reset}\x1b[K`);

    drawHR(4, 3, Math.min(cols - 6, 70));
    renderTabs(5);
    renderContent();
  },

  onKey(key: KeyEvent) {
    const { rows } = getTermSize();
    const maxLines = rows - 8;

    // Tab switching
    if (key.name === "1") { view = "log"; scrollOffset = 0; refresh(); app.requestRender(); }
    else if (key.name === "2") { view = "status"; scrollOffset = 0; loadStatus(); app.requestRender(); }
    else if (key.name === "3") { view = "branches"; scrollOffset = 0; loadBranches(); app.requestRender(); }
    else if (key.name === "4") { view = "prs"; scrollOffset = 0; loadPRs(); app.requestRender(); }
    else if (key.name === "5") { view = "diff"; scrollOffset = 0; loadDiff(); app.requestRender(); }
    else if (key.name === "tab") {
      const order: View[] = ["log", "status", "branches", "prs", "diff"];
      view = order[(order.indexOf(view) + 1) % order.length]!;
      scrollOffset = 0;
      refresh();
      app.requestRender();
    }

    // Scroll
    else if (key.name === "j" || key.name === "down") { scrollOffset++; app.requestRender(); }
    else if (key.name === "k" || key.name === "up") { scrollOffset = Math.max(0, scrollOffset - 1); app.requestRender(); }
    else if (key.name === "pagedown") { scrollOffset += maxLines; app.requestRender(); }
    else if (key.name === "pageup") { scrollOffset = Math.max(0, scrollOffset - maxLines); app.requestRender(); }

    // Refresh
    else if (key.name === "r") { refresh(); app.requestRender(); app.flash("Refreshed"); }

    // Status actions
    else if (key.name === "f" && view === "status") {
      app.flash("Fetching...");
      const r = runAction("git fetch --all --prune");
      app.flash(r.split("\n")[0] || "Fetched");
      refresh(); app.requestRender();
    }
    else if (key.name === "p" && view === "status") {
      app.flash("Pulling...");
      const r = runAction("git pull");
      app.flash(r.split("\n")[0] || "Pulled");
      refresh(); app.requestRender();
    }
    else if (key.name === "P" && view === "status") {
      app.flash("Pushing...");
      const r = runAction("git push");
      app.flash(r.split("\n")[0] || "Pushed");
      refresh(); app.requestRender();
    }
    else if (key.name === "s" && view === "status") {
      runAction("git add -A");
      app.flash("Staged all");
      loadStatus(); app.requestRender();
    }

    // Branch checkout
    else if (key.name === "return" && view === "branches") {
      const line = branchLines[scrollOffset];
      if (line) {
        const branch = line.replace(/^\*?\s*/, "").split(/\s+/)[0];
        if (branch && !branch.startsWith("remotes/") && branch !== currentBranch) {
          const r = runAction(`git checkout ${branch}`);
          app.flash(r.split("\n")[0] || `→ ${branch}`);
          refresh(); app.requestRender();
        }
      }
    }

    // PR checkout
    else if (key.name === "return" && view === "prs") {
      const line = prLines[scrollOffset];
      if (line) {
        const match = line.match(/^#(\d+)/);
        if (match) {
          app.flash(`Checking out PR #${match[1]}...`);
          const r = runAction(`gh pr checkout ${match[1]}`);
          app.flash(r.split("\n")[0] || `→ PR #${match[1]}`);
          refresh(); app.requestRender();
        }
      }
    }

    // Back
    else if (key.name === "escape") { app.back(); }
  },
};
