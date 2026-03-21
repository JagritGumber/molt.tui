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
let selectedIndex = 0;

// Cached data
let logLines: string[] = [];
let logCommitIndices: number[] = []; // maps selectable index → logLines index
let statusLines: string[] = [];
let branchLines: string[] = [];
let prLines: string[] = [];
let diffLines: string[] = [];
let currentBranch = "";
let repoName = "";

// Commit data for actions
interface CommitInfo { hash: string; refs: string; subject: string }
let commits: CommitInfo[] = [];

// All commands are hardcoded — no user input interpolated, safe for local TUI
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

// ── Branch colors ──
const BRANCH_COLORS = [
  fg.brightCyan, fg.brightMagenta, fg.brightGreen, fg.brightYellow,
  fg.brightBlue, fg.brightRed, fg.cyan, fg.magenta,
];

function loadLog() {
  const raw = run("git log --all --format='%h|%p|%D|%s|%cr|%an' -60");
  if (!raw) { logLines = ["(no commits)"]; logCommitIndices = []; commits = []; return; }

  const parsed = raw.split("\n").map((line) => {
    const [hash, parents, refs, subject, date, author] = line.split("|");
    return {
      hash: hash || "", parents: (parents || "").split(" ").filter(Boolean),
      refs: refs || "", subject: subject || "", date: date || "", author: author || "",
    };
  });

  commits = parsed.map((c) => ({ hash: c.hash, refs: c.refs, subject: c.subject }));

  // Build connected graph
  const lanes: string[] = [];
  const laneColors: string[] = [];
  let colorIdx = 0;
  const nextColor = () => BRANCH_COLORS[colorIdx++ % BRANCH_COLORS.length]!;
  const getLaneColor = (col: number) => laneColors[col] || fg.gray;

  logLines = [];
  logCommitIndices = [];
  let commitIdx = 0;

  for (const commit of parsed) {
    let col = lanes.indexOf(commit.hash);
    if (col === -1) {
      col = lanes.indexOf("");
      if (col === -1) { col = lanes.length; lanes.push(""); laneColors.push(""); }
      lanes[col] = commit.hash;
      laneColors[col] = nextColor();
    }

    const myColor = getLaneColor(col);
    const numLanes = lanes.length;

    // Commit row
    let commitRow = "";
    for (let i = 0; i < numLanes; i++) {
      if (i === col) commitRow += `${myColor}●${style.reset}`;
      else if (lanes[i]) commitRow += `${getLaneColor(i)}│${style.reset}`;
      else commitRow += " ";
      commitRow += " ";
    }

    const hashStr = `${fg.yellow}${commit.hash}${style.reset}`;
    const refStr = commit.refs ? ` ${fg.brightGreen}${style.bold}(${commit.refs})${style.reset}` : "";
    const subjStr = `${fg.white}${commit.subject}${style.reset}`;
    const dateStr = ` ${fg.gray}${commit.date}${style.reset}`;

    logCommitIndices.push(logLines.length);
    logLines.push(`${commitRow}${hashStr}${refStr} ${subjStr}${dateStr}`);
    commitIdx++;

    // Lane updates
    const prevLanes = [...lanes];
    if (commit.parents.length === 0) {
      lanes[col] = "";
    } else {
      lanes[col] = commit.parents[0] || "";
      for (let p = 1; p < commit.parents.length; p++) {
        const ph = commit.parents[p]!;
        if (lanes.includes(ph)) continue;
        const free = lanes.indexOf("");
        if (free !== -1 && free !== col) { lanes[free] = ph; laneColors[free] = nextColor(); }
        else { lanes.push(ph); laneColors.push(nextColor()); }
      }
    }

    // Connector row for merges
    if (commit.parents.length > 1) {
      const mergeTargets: number[] = [];
      for (let p = 1; p < commit.parents.length; p++) {
        const ph = commit.parents[p]!;
        const lane = lanes.indexOf(ph);
        if (lane !== -1 && lane !== col) mergeTargets.push(lane);
      }

      if (mergeTargets.length > 0) {
        const maxL = Math.max(prevLanes.length, lanes.length);
        const minMerge = Math.min(col, ...mergeTargets);
        const maxMerge = Math.max(col, ...mergeTargets);
        let connRow = "";

        for (let i = 0; i < maxL; i++) {
          const isActive = i < lanes.length && lanes[i] !== "";
          const isMergeEnd = mergeTargets.includes(i);

          if (i === col) connRow += `${myColor}├${style.reset}`;
          else if (isMergeEnd) connRow += `${getLaneColor(i)}╮${style.reset}`;
          else if (i > minMerge && i < maxMerge) {
            if (isActive && !isMergeEnd && i !== col) connRow += `${getLaneColor(i)}┼${style.reset}`;
            else connRow += `${myColor}─${style.reset}`;
          }
          else if (isActive) connRow += `${getLaneColor(i)}│${style.reset}`;
          else connRow += " ";
          connRow += " ";
        }
        logLines.push(connRow);
      }
    }
  }
}

function loadStatus() {
  const raw = run("git status --short");
  statusLines = raw ? raw.split("\n") : ["(clean working tree)"];
}

function loadBranches() {
  const raw = run("git branch --sort=-committerdate --format='%(HEAD)|%(refname:short)|%(committerdate:relative)|%(subject)'");
  branchLines = raw ? raw.split("\n").slice(0, 30) : ["(no branches)"];
}

function loadPRs() {
  const raw = run("gh pr list --limit 15 --json number,title,state,headRefName,author --template '{{range .}}#{{.number}} {{.state}} {{.headRefName}} {{.title}} ({{.author.login}}){{\"\\n\"}}{{end}}'");
  prLines = raw ? raw.split("\n").filter(Boolean) : ["(no PRs or gh not authenticated)"];
}

function loadDiff(ref?: string) {
  const target = ref || "";
  const raw = run(`git diff ${target} --stat`);
  const full = run(`git diff ${target} --no-color`);
  diffLines = raw ? [...raw.split("\n"), "", ...full.split("\n").slice(0, 200)] : ["(no changes)"];
}

function loadCommitDiff(hash: string) {
  const raw = run(`git show ${hash} --stat --no-color`);
  const full = run(`git show ${hash} --no-color`);
  diffLines = raw ? [...raw.split("\n"), "", ...full.split("\n").slice(0, 200)] : ["(no changes)"];
}

// ── Coloring ──

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
  if (line.startsWith("diff ") || line.startsWith("index ") || line.startsWith("commit ")) return `${fg.brightMagenta}${style.bold}${line}${style.reset}`;
  if (line.startsWith("Author:") || line.startsWith("Date:")) return `${fg.brightYellow}${line}${style.reset}`;
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

function getSelectableLines(): string[] {
  switch (view) {
    case "log": return logLines;
    case "status": return statusLines;
    case "branches": return branchLines;
    case "prs": return prLines;
    case "diff": return diffLines;
    default: return [];
  }
}

function getSelectableCount(): number {
  switch (view) {
    case "log": return commits.length;
    case "branches": return branchLines.length;
    case "prs": return prLines.length;
    case "status": return statusLines.length;
    default: return 0;
  }
}

function renderContent() {
  const { rows, cols } = getTermSize();
  const w = cols - 6;
  const maxLines = rows - 8;
  const lines = getSelectableLines();
  const selectable = view !== "diff";

  // Clamp
  const maxScroll = Math.max(0, lines.length - maxLines);
  if (scrollOffset > maxScroll) scrollOffset = maxScroll;

  // For log view, map selectedIndex to the actual logLines index
  let highlightLine = -1;
  if (view === "log" && selectedIndex < logCommitIndices.length) {
    highlightLine = logCommitIndices[selectedIndex]!;
    // Auto-scroll to keep selection visible
    if (highlightLine < scrollOffset) scrollOffset = highlightLine;
    if (highlightLine >= scrollOffset + maxLines) scrollOffset = highlightLine - maxLines + 1;
  } else if (selectable) {
    highlightLine = selectedIndex;
    if (highlightLine < scrollOffset) scrollOffset = highlightLine;
    if (highlightLine >= scrollOffset + maxLines) scrollOffset = highlightLine - maxLines + 1;
  }

  for (let i = 0; i < maxLines; i++) {
    const idx = scrollOffset + i;
    cursor.to(6 + i, 3);
    if (idx >= lines.length) { write("\x1b[K"); continue; }

    const line = lines[idx]!.replace(/[\n\r]/g, "");
    const isSelected = selectable && idx === highlightLine;

    if (view === "log") {
      // Log is pre-colored, just add selection marker
      if (isSelected) {
        write(`${bg.rgb(30, 30, 50)}${fg.brightCyan}❯${style.reset}${bg.rgb(30, 30, 50)}${line.slice(0, w)}${style.reset}\x1b[K`);
      } else {
        write(` ${line.slice(0, w)}\x1b[K`);
      }
    } else if (view === "status") {
      const colored = colorStatusLine(line);
      if (isSelected) {
        write(`${bg.rgb(30, 30, 50)}${fg.brightCyan}❯${style.reset}${bg.rgb(30, 30, 50)}${colored}${style.reset}\x1b[K`);
      } else {
        write(` ${colored}\x1b[K`);
      }
    } else if (view === "branches") {
      const parts = line.split("|");
      const isCurrent = parts[0]?.trim() === "*";
      const name = parts[1] || "";
      const date = parts[2] || "";
      const subj = (parts[3] || "").slice(0, 40);
      const branchColor = isCurrent ? `${fg.brightCyan}${style.bold}` : fg.white;
      const marker = isCurrent ? "●" : " ";
      const formatted = `${branchColor}${marker} ${name.padEnd(25)}${style.reset} ${fg.gray}${date.padEnd(18)}${fg.white}${subj}${style.reset}`;
      if (isSelected) {
        write(`${bg.rgb(30, 30, 50)}${fg.brightCyan}❯${style.reset}${bg.rgb(30, 30, 50)}${formatted}${style.reset}\x1b[K`);
      } else {
        write(` ${formatted}\x1b[K`);
      }
    } else if (view === "prs") {
      let colored = `${fg.white}${line}${style.reset}`;
      if (line.includes("OPEN")) colored = line.replace("OPEN", `${fg.brightGreen}OPEN${style.reset}`);
      else if (line.includes("MERGED")) colored = line.replace("MERGED", `${fg.brightMagenta}MERGED${style.reset}`);
      else if (line.includes("CLOSED")) colored = line.replace("CLOSED", `${fg.brightRed}CLOSED${style.reset}`);
      if (isSelected) {
        write(`${bg.rgb(30, 30, 50)}${fg.brightCyan}❯${style.reset}${bg.rgb(30, 30, 50)}${colored}${style.reset}\x1b[K`);
      } else {
        write(` ${colored}\x1b[K`);
      }
    } else {
      // Diff — no selection, just color
      write(` ${colorDiffLine(line.slice(0, w))}\x1b[K`);
    }
  }

  // Info bar
  cursor.to(rows - 3, 3);
  let info = "";
  if (view === "log") {
    const c = commits[selectedIndex];
    info = c
      ? `${fg.brightCyan}enter${fg.white} view diff  ${fg.brightCyan}b${fg.white} checkout  ${fg.brightCyan}c${fg.white} cherry-pick  ${fg.gray}${c.hash}${style.reset}`
      : "";
  } else if (view === "status") {
    info = `${fg.brightCyan}f${fg.white} fetch  ${fg.brightCyan}p${fg.white} pull  ${fg.brightCyan}P${fg.white} push  ${fg.brightCyan}s${fg.white} stage all  ${fg.brightCyan}a${fg.white} stage file${style.reset}`;
  } else if (view === "branches") {
    info = `${fg.brightCyan}enter${fg.white} checkout  ${fg.brightCyan}n${fg.white} new branch  ${fg.brightCyan}D${fg.white} delete  ${fg.brightCyan}m${fg.white} merge into current${style.reset}`;
  } else if (view === "prs") {
    info = `${fg.brightCyan}enter${fg.white} checkout PR  ${fg.brightCyan}r${fg.white} refresh${style.reset}`;
  } else {
    info = `${fg.gray}${scrollOffset + 1}-${Math.min(scrollOffset + maxLines, lines.length)} of ${lines.length}${style.reset}`;
  }
  write(`${info}\x1b[K`);
}

// ── Screen ──

export const gitScreen: Screen = {
  name: "git",
  statusHint: "1-5 tabs • j/k select • enter action • r refresh • esc back",

  onEnter() {
    view = "log";
    scrollOffset = 0;
    selectedIndex = 0;
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
    const maxSelectable = getSelectableCount();

    // Tab switching
    if (key.name === "1") { view = "log"; scrollOffset = 0; selectedIndex = 0; refresh(); app.requestRender(); }
    else if (key.name === "2") { view = "status"; scrollOffset = 0; selectedIndex = 0; loadStatus(); app.requestRender(); }
    else if (key.name === "3") { view = "branches"; scrollOffset = 0; selectedIndex = 0; loadBranches(); app.requestRender(); }
    else if (key.name === "4") { view = "prs"; scrollOffset = 0; selectedIndex = 0; loadPRs(); app.requestRender(); }
    else if (key.name === "5") { view = "diff"; scrollOffset = 0; selectedIndex = 0; loadDiff(); app.requestRender(); }
    else if (key.name === "tab") {
      const order: View[] = ["log", "status", "branches", "prs", "diff"];
      view = order[(order.indexOf(view) + 1) % order.length]!;
      scrollOffset = 0; selectedIndex = 0;
      refresh(); app.requestRender();
    }

    // Selection movement
    else if (key.name === "j" || key.name === "down") {
      if (view === "diff") { scrollOffset++; }
      else { selectedIndex = Math.min(maxSelectable - 1, selectedIndex + 1); }
      app.requestRender();
    }
    else if (key.name === "k" || key.name === "up") {
      if (view === "diff") { scrollOffset = Math.max(0, scrollOffset - 1); }
      else { selectedIndex = Math.max(0, selectedIndex - 1); }
      app.requestRender();
    }
    else if (key.name === "pagedown") {
      const { rows } = getTermSize();
      const jump = rows - 8;
      if (view === "diff") scrollOffset += jump;
      else selectedIndex = Math.min(maxSelectable - 1, selectedIndex + jump);
      app.requestRender();
    }
    else if (key.name === "pageup") {
      const { rows } = getTermSize();
      const jump = rows - 8;
      if (view === "diff") scrollOffset = Math.max(0, scrollOffset - jump);
      else selectedIndex = Math.max(0, selectedIndex - jump);
      app.requestRender();
    }

    // Refresh
    else if (key.name === "r") { refresh(); app.requestRender(); app.flash("Refreshed"); }

    // ── Log actions ──
    else if (key.name === "return" && view === "log") {
      const c = commits[selectedIndex];
      if (c) {
        loadCommitDiff(c.hash);
        view = "diff"; scrollOffset = 0;
        app.requestRender();
      }
    }
    else if (key.name === "b" && view === "log") {
      // Checkout the ref at this commit
      const c = commits[selectedIndex];
      if (c?.refs) {
        const branch = c.refs.split(",")[0]!.trim().replace("HEAD -> ", "");
        if (branch && branch !== currentBranch) {
          const r = runAction(`git checkout ${branch}`);
          app.flash(r.split("\n")[0] || `→ ${branch}`);
          refresh(); app.requestRender();
        }
      } else {
        app.flash("No branch ref at this commit");
      }
    }
    else if (key.name === "c" && view === "log") {
      const c = commits[selectedIndex];
      if (c) {
        const r = runAction(`git cherry-pick ${c.hash}`);
        app.flash(r.split("\n")[0] || `Cherry-picked ${c.hash}`);
        refresh(); app.requestRender();
      }
    }

    // ── Status actions ──
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
    else if (key.name === "a" && view === "status") {
      // Stage selected file
      const line = statusLines[selectedIndex];
      if (line) {
        const file = line.slice(3).trim();
        if (file) {
          runAction(`git add "${file}"`);
          app.flash(`Staged ${file}`);
          loadStatus(); app.requestRender();
        }
      }
    }
    else if (key.name === "return" && view === "status") {
      // View diff of selected file
      const line = statusLines[selectedIndex];
      if (line) {
        const file = line.slice(3).trim();
        if (file) {
          const raw = run(`git diff "${file}" --no-color`);
          diffLines = raw ? raw.split("\n") : ["(no changes)"];
          view = "diff"; scrollOffset = 0;
          app.requestRender();
        }
      }
    }

    // ── Branch actions ──
    else if (key.name === "return" && view === "branches") {
      const line = branchLines[selectedIndex];
      if (line) {
        const branch = line.split("|")[1]?.trim();
        if (branch && branch !== currentBranch) {
          const r = runAction(`git checkout ${branch}`);
          app.flash(r.split("\n")[0] || `→ ${branch}`);
          refresh(); app.requestRender();
        }
      }
    }
    else if (key.name === "D" && view === "branches") {
      const line = branchLines[selectedIndex];
      if (line) {
        const branch = line.split("|")[1]?.trim();
        if (branch && branch !== currentBranch) {
          const r = runAction(`git branch -d ${branch}`);
          app.flash(r.split("\n")[0] || `Deleted ${branch}`);
          loadBranches(); app.requestRender();
        } else {
          app.flash("Can't delete current branch");
        }
      }
    }
    else if (key.name === "m" && view === "branches") {
      const line = branchLines[selectedIndex];
      if (line) {
        const branch = line.split("|")[1]?.trim();
        if (branch && branch !== currentBranch) {
          const r = runAction(`git merge ${branch}`);
          app.flash(r.split("\n")[0] || `Merged ${branch}`);
          refresh(); app.requestRender();
        }
      }
    }

    // ── PR actions ──
    else if (key.name === "return" && view === "prs") {
      const line = prLines[selectedIndex];
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

    // Back — from diff go back to previous view, otherwise exit
    else if (key.name === "escape") {
      if (view === "diff") {
        view = "log"; scrollOffset = 0;
        refresh(); app.requestRender();
      } else {
        app.back();
      }
    }
  },
};
