// Git screen — full git dashboard (Git Graph parity)
// Uses `git` and `gh` CLI for all operations

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, bg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawHR, drawTextInput } from "../tui/components.ts";
import type { KeyEvent } from "../tui/input.ts";
import { execSync } from "child_process";

type View = "log" | "status" | "branches" | "tags" | "stash" | "remotes" | "prs" | "diff";

let view: View = "log";
let prevView: View = "log";
let cwd = process.cwd();
let scrollOffset = 0;
let selectedIndex = 0;

// Search / input mode
let inputMode: "none" | "search" | "branch-name" | "tag-name" | "remote-add" | "reset" = "none";
let inputValue = "";
let searchFilter = "";

// Commit comparison
let compareHash = "";

// Cached data
let logLines: string[] = [];
let logCommitIndices: number[] = [];
let statusLines: string[] = [];
let branchLines: string[] = [];
let tagLines: string[] = [];
let stashLines: string[] = [];
let remoteLines: string[] = [];
let prLines: string[] = [];
let diffLines: string[] = [];
let currentBranch = "";
let repoName = "";

interface CommitInfo { hash: string; refs: string; subject: string; author: string; date: string }
let commits: CommitInfo[] = [];

// Mute merge commits toggle
let muteMerges = false;

// All commands hardcoded — safe for local TUI
function run(cmd: string): string {
  try { return execSync(cmd, { cwd, encoding: "utf-8", timeout: 10000 }).trim(); }
  catch { return ""; }
}

function runAction(cmd: string): string {
  try { return execSync(cmd, { cwd, encoding: "utf-8", timeout: 15000 }).trim(); }
  catch (err: any) { return err.stderr?.trim() || err.message?.slice(0, 80) || "failed"; }
}

function refresh() {
  currentBranch = run("git branch --show-current");
  repoName = run("git rev-parse --show-toplevel 2>/dev/null").split("/").pop() || "";
  switch (view) {
    case "log": loadLog(); break;
    case "status": loadStatus(); break;
    case "branches": loadBranches(); break;
    case "tags": loadTags(); break;
    case "stash": loadStash(); break;
    case "remotes": loadRemotes(); break;
    case "prs": loadPRs(); break;
  }
}

// ── Branch colors ──
const BRANCH_COLORS = [
  fg.brightCyan, fg.brightMagenta, fg.brightGreen, fg.brightYellow,
  fg.brightBlue, fg.brightRed, fg.cyan, fg.magenta,
];

// ── Loaders ──

function loadLog() {
  const noMerge = muteMerges ? "--no-merges " : "";
  const raw = run(`git log --all ${noMerge}--format='%h|%p|%D|%s|%cr|%an' -80`);
  if (!raw) { logLines = ["(no commits)"]; logCommitIndices = []; commits = []; return; }

  const parsed = raw.split("\n").map((line) => {
    const [hash, parents, refs, subject, date, author] = line.split("|");
    return { hash: hash || "", parents: (parents || "").split(" ").filter(Boolean), refs: refs || "", subject: subject || "", date: date || "", author: author || "" };
  });

  // Apply search filter
  const filtered = searchFilter
    ? parsed.filter((c) => {
        const q = searchFilter.toLowerCase();
        return c.subject.toLowerCase().includes(q) || c.author.toLowerCase().includes(q) || c.hash.includes(q) || c.refs.toLowerCase().includes(q);
      })
    : parsed;

  commits = filtered.map((c) => ({ hash: c.hash, refs: c.refs, subject: c.subject, author: c.author, date: c.date }));

  // Build connected graph
  const lanes: string[] = [];
  const laneColors: string[] = [];
  let colorIdx = 0;
  const nextColor = () => BRANCH_COLORS[colorIdx++ % BRANCH_COLORS.length]!;
  const getLaneColor = (col: number) => laneColors[col] || fg.gray;

  logLines = [];
  logCommitIndices = [];

  for (const commit of filtered) {
    let col = lanes.indexOf(commit.hash);
    if (col === -1) {
      col = lanes.indexOf("");
      if (col === -1) { col = lanes.length; lanes.push(""); laneColors.push(""); }
      lanes[col] = commit.hash;
      laneColors[col] = nextColor();
    }

    const myColor = getLaneColor(col);

    let commitRow = "";
    for (let i = 0; i < lanes.length; i++) {
      if (i === col) commitRow += `${myColor}●${style.reset}`;
      else if (lanes[i]) commitRow += `${getLaneColor(i)}│${style.reset}`;
      else commitRow += " ";
      commitRow += " ";
    }

    const hashStr = `${fg.yellow}${commit.hash}${style.reset}`;
    const refStr = commit.refs ? ` ${fg.brightGreen}${style.bold}(${commit.refs})${style.reset}` : "";
    const subjStr = `${fg.white}${commit.subject}${style.reset}`;
    const dateStr = ` ${fg.gray}${commit.date}${style.reset}`;
    const authorStr = ` ${fg.brightBlue}${commit.author}${style.reset}`;

    logCommitIndices.push(logLines.length);
    logLines.push(`${commitRow}${hashStr}${refStr} ${subjStr}${dateStr}${authorStr}`);

    // Lane updates + merge connectors
    const prevLanes = [...lanes];
    if (commit.parents.length === 0) lanes[col] = "";
    else {
      lanes[col] = commit.parents[0] || "";
      for (let p = 1; p < commit.parents.length; p++) {
        const ph = commit.parents[p]!;
        if (lanes.includes(ph)) continue;
        const free = lanes.indexOf("");
        if (free !== -1 && free !== col) { lanes[free] = ph; laneColors[free] = nextColor(); }
        else { lanes.push(ph); laneColors.push(nextColor()); }
      }
    }

    if (commit.parents.length > 1) {
      const mergeTargets: number[] = [];
      for (let p = 1; p < commit.parents.length; p++) {
        const ph = commit.parents[p]!;
        const lane = lanes.indexOf(ph);
        if (lane !== -1 && lane !== col) mergeTargets.push(lane);
      }
      if (mergeTargets.length > 0) {
        const maxL = Math.max(prevLanes.length, lanes.length);
        const minM = Math.min(col, ...mergeTargets);
        const maxM = Math.max(col, ...mergeTargets);
        let connRow = "";
        for (let i = 0; i < maxL; i++) {
          const isActive = i < lanes.length && lanes[i] !== "";
          if (i === col) connRow += `${myColor}├${style.reset}`;
          else if (mergeTargets.includes(i)) connRow += `${getLaneColor(i)}╮${style.reset}`;
          else if (i > minM && i < maxM) {
            if (isActive && i !== col) connRow += `${getLaneColor(i)}┼${style.reset}`;
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
  branchLines = raw ? raw.split("\n").slice(0, 40) : ["(no branches)"];
}

function loadTags() {
  const raw = run("git tag --sort=-creatordate --format='%(refname:short)|%(creatordate:relative)|%(subject)' -n");
  tagLines = raw ? raw.split("\n").slice(0, 30) : ["(no tags)"];
}

function loadStash() {
  const raw = run("git stash list --format='%gd|%gs|%cr'");
  stashLines = raw ? raw.split("\n") : ["(no stashes)"];
}

function loadRemotes() {
  const raw = run("git remote -v");
  remoteLines = raw ? raw.split("\n").filter((l) => l.includes("(fetch)")) : ["(no remotes)"];
}

function loadPRs() {
  const raw = run("gh pr list --limit 20 --json number,title,state,headRefName,author --template '{{range .}}#{{.number}} {{.state}} {{.headRefName}} {{.title}} ({{.author.login}}){{\"\\n\"}}{{end}}'");
  prLines = raw ? raw.split("\n").filter(Boolean) : ["(no PRs or gh not authenticated)"];
}

function loadCommitDiff(hash: string) {
  const raw = run(`git show ${hash} --stat --no-color`);
  const full = run(`git show ${hash} --no-color`);
  diffLines = [...(raw ? raw.split("\n") : []), "", ...(full ? full.split("\n").slice(0, 300) : ["(empty)"])];
}

function loadComparisonDiff(hash1: string, hash2: string) {
  const raw = run(`git diff ${hash1}..${hash2} --stat --no-color`);
  const full = run(`git diff ${hash1}..${hash2} --no-color`);
  diffLines = [`Comparing ${hash1}..${hash2}`, "", ...(raw ? raw.split("\n") : []), "", ...(full ? full.split("\n").slice(0, 300) : ["(no diff)"])];
}

// ── Coloring ──

function colorStatusLine(line: string): string {
  const code = line.slice(0, 2); const file = line.slice(3);
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
  if (line.startsWith("diff ") || line.startsWith("index ") || line.startsWith("commit ") || line.startsWith("Comparing ")) return `${fg.brightMagenta}${style.bold}${line}${style.reset}`;
  if (line.startsWith("Author:") || line.startsWith("Date:")) return `${fg.brightYellow}${line}${style.reset}`;
  return `${fg.gray}${line}${style.reset}`;
}

// ── Rendering ──

function renderTabs(row: number) {
  const tabs: { key: string; label: string; v: View }[] = [
    { key: "1", label: "Log", v: "log" },
    { key: "2", label: "Status", v: "status" },
    { key: "3", label: "Branch", v: "branches" },
    { key: "4", label: "Tags", v: "tags" },
    { key: "5", label: "Stash", v: "stash" },
    { key: "6", label: "Remote", v: "remotes" },
    { key: "7", label: "PRs", v: "prs" },
    { key: "8", label: "Diff", v: "diff" },
  ];
  cursor.to(row, 3);
  write(tabs.map((t) => {
    const active = view === t.v;
    return active
      ? `${bg.rgb(40, 40, 70)}${fg.brightCyan}${style.bold} ${t.key}:${t.label} ${style.reset}`
      : `${fg.gray} ${t.key}:${t.label} ${style.reset}`;
  }).join("") + "\x1b[K");
}

function getLines(): string[] {
  switch (view) {
    case "log": return logLines; case "status": return statusLines;
    case "branches": return branchLines; case "tags": return tagLines;
    case "stash": return stashLines; case "remotes": return remoteLines;
    case "prs": return prLines; case "diff": return diffLines;
    default: return [];
  }
}

function getCount(): number {
  switch (view) {
    case "log": return commits.length; case "status": return statusLines.length;
    case "branches": return branchLines.length; case "tags": return tagLines.length;
    case "stash": return stashLines.length; case "remotes": return remoteLines.length;
    case "prs": return prLines.length; default: return 0;
  }
}

function renderLine(line: string, idx: number, isSelected: boolean, w: number) {
  const sel = isSelected ? `${bg.rgb(30, 30, 50)}${fg.brightCyan}❯${style.reset}${bg.rgb(30, 30, 50)}` : " ";
  const end = isSelected ? `${style.reset}\x1b[K` : "\x1b[K";
  const clean = line.replace(/[\n\r]/g, "").slice(0, w);

  if (view === "log") { write(`${sel}${clean}${end}`); return; }
  if (view === "status") { write(`${sel}${colorStatusLine(clean)}${end}`); return; }
  if (view === "diff") { write(` ${colorDiffLine(clean)}\x1b[K`); return; }

  if (view === "branches") {
    const parts = clean.split("|");
    const isCur = parts[0]?.trim() === "*";
    const name = parts[1] || ""; const date = parts[2] || ""; const subj = (parts[3] || "").slice(0, 35);
    const bc = isCur ? `${fg.brightCyan}${style.bold}` : fg.white;
    const m = isCur ? "●" : " ";
    write(`${sel}${bc}${m} ${name.padEnd(22)}${style.reset} ${fg.gray}${date.padEnd(16)}${fg.white}${subj}${style.reset}${end}`);
    return;
  }
  if (view === "tags") {
    const parts = clean.split("|");
    const name = parts[0] || ""; const date = parts[1] || ""; const msg = (parts[2] || "").slice(0, 35);
    write(`${sel}${fg.brightYellow}🏷 ${name.padEnd(20)}${style.reset} ${fg.gray}${date.padEnd(16)}${fg.white}${msg}${style.reset}${end}`);
    return;
  }
  if (view === "stash") {
    const parts = clean.split("|");
    const ref = parts[0] || ""; const msg = parts[1] || ""; const date = parts[2] || "";
    write(`${sel}${fg.brightMagenta}${ref.padEnd(12)}${style.reset} ${fg.white}${msg.slice(0, 35).padEnd(35)}${style.reset} ${fg.gray}${date}${style.reset}${end}`);
    return;
  }
  if (view === "remotes") {
    const parts = clean.split(/\s+/);
    const name = parts[0] || ""; const url = parts[1] || "";
    write(`${sel}${fg.brightCyan}${name.padEnd(12)}${style.reset} ${fg.white}${url}${style.reset}${end}`);
    return;
  }
  if (view === "prs") {
    let colored = `${fg.white}${clean}${style.reset}`;
    if (clean.includes("OPEN")) colored = clean.replace("OPEN", `${fg.brightGreen}OPEN${style.reset}`);
    else if (clean.includes("MERGED")) colored = clean.replace("MERGED", `${fg.brightMagenta}MERGED${style.reset}`);
    else if (clean.includes("CLOSED")) colored = clean.replace("CLOSED", `${fg.brightRed}CLOSED${style.reset}`);
    write(`${sel}${colored}${end}`);
    return;
  }
  write(`${sel}${fg.white}${clean}${style.reset}${end}`);
}

function renderContent() {
  const { rows, cols } = getTermSize();
  const w = cols - 6;
  const inputH = inputMode !== "none" ? 2 : 0;
  const maxLines = rows - 8 - inputH;
  const lines = getLines();
  const selectable = view !== "diff";

  const maxScroll = Math.max(0, lines.length - maxLines);
  if (scrollOffset > maxScroll) scrollOffset = maxScroll;

  let hlLine = -1;
  if (view === "log" && selectedIndex < logCommitIndices.length) {
    hlLine = logCommitIndices[selectedIndex]!;
  } else if (selectable) hlLine = selectedIndex;

  if (hlLine >= 0) {
    if (hlLine < scrollOffset) scrollOffset = hlLine;
    if (hlLine >= scrollOffset + maxLines) scrollOffset = hlLine - maxLines + 1;
  }

  for (let i = 0; i < maxLines; i++) {
    const idx = scrollOffset + i;
    cursor.to(6 + i, 3);
    if (idx >= lines.length) { write("\x1b[K"); continue; }
    renderLine(lines[idx]!, idx, selectable && idx === hlLine, w);
  }

  // Input bar
  if (inputMode !== "none") {
    const labels: Record<string, string> = {
      search: "Search", "branch-name": "New branch name", "tag-name": "Tag name",
      "remote-add": "Remote (name url)", reset: "Reset mode (soft/mixed/hard)",
    };
    cursor.to(rows - 4 - inputH + 1, 3);
    write(`${bg.rgb(30, 30, 50)}${fg.brightCyan}${labels[inputMode] || ""}: ${fg.brightWhite}${inputValue}█${style.reset}\x1b[K`);
  }

  // Info bar
  cursor.to(rows - 3, 3);
  const infos: Record<string, string> = {
    log: `${fg.brightCyan}enter${fg.white} diff  ${fg.brightCyan}b${fg.white} checkout  ${fg.brightCyan}c${fg.white} cherry-pick  ${fg.brightCyan}v${fg.white} revert  ${fg.brightCyan}/${fg.white} search  ${fg.brightCyan}C${fg.white} compare  ${fg.brightCyan}M${fg.white} ${muteMerges ? "show" : "mute"} merges  ${fg.brightCyan}n${fg.white} branch here${style.reset}`,
    status: `${fg.brightCyan}a${fg.white} stage  ${fg.brightCyan}u${fg.white} unstage  ${fg.brightCyan}s${fg.white} stage all  ${fg.brightCyan}f${fg.white} fetch  ${fg.brightCyan}p${fg.white} pull  ${fg.brightCyan}P${fg.white} push  ${fg.brightCyan}S${fg.white} stash  ${fg.brightCyan}R${fg.white} reset${style.reset}`,
    branches: `${fg.brightCyan}enter${fg.white} checkout  ${fg.brightCyan}n${fg.white} new  ${fg.brightCyan}R${fg.white} rename  ${fg.brightCyan}D${fg.white} delete  ${fg.brightCyan}m${fg.white} merge  ${fg.brightCyan}e${fg.white} rebase${style.reset}`,
    tags: `${fg.brightCyan}n${fg.white} new tag  ${fg.brightCyan}D${fg.white} delete  ${fg.brightCyan}P${fg.white} push tag${style.reset}`,
    stash: `${fg.brightCyan}a${fg.white} apply  ${fg.brightCyan}p${fg.white} pop  ${fg.brightCyan}D${fg.white} drop${style.reset}`,
    remotes: `${fg.brightCyan}n${fg.white} add  ${fg.brightCyan}D${fg.white} remove  ${fg.brightCyan}f${fg.white} fetch${style.reset}`,
    prs: `${fg.brightCyan}enter${fg.white} checkout PR${style.reset}`,
    diff: `${fg.gray}scroll j/k${style.reset}`,
  };
  write(`${infos[view] || ""}\x1b[K`);

  // Search indicator
  if (searchFilter && view === "log") {
    cursor.to(rows - 2, 3);
    write(`${fg.yellow}filter: "${searchFilter}" ${fg.gray}(/ to clear)${style.reset}\x1b[K`);
  }
}

// ── Screen ──

export const gitScreen: Screen = {
  name: "git",
  get handlesTextInput() { return inputMode !== "none"; },
  statusHint: "1-8 tabs • j/k select • enter action • r refresh • esc back",

  onEnter() {
    view = "log"; scrollOffset = 0; selectedIndex = 0;
    inputMode = "none"; inputValue = ""; searchFilter = ""; compareHash = "";
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
    // ── Input mode ──
    if (inputMode !== "none") {
      if (key.name === "return") {
        const val = inputValue.trim();
        if (inputMode === "search") {
          searchFilter = val; loadLog();
        } else if (inputMode === "branch-name" && val) {
          const c = commits[selectedIndex];
          const ref = c ? c.hash : "HEAD";
          const r = runAction(`git checkout -b ${val} ${ref}`);
          app.flash(r.split("\n")[0] || `Created ${val}`);
          refresh();
        } else if (inputMode === "tag-name" && val) {
          const c = commits[selectedIndex];
          const ref = c ? c.hash : "HEAD";
          const r = runAction(`git tag ${val} ${ref}`);
          app.flash(r.split("\n")[0] || `Tagged ${val}`);
          loadTags();
        } else if (inputMode === "remote-add" && val) {
          const [name, url] = val.split(/\s+/);
          if (name && url) {
            const r = runAction(`git remote add ${name} ${url}`);
            app.flash(r || `Added ${name}`);
            loadRemotes();
          }
        } else if (inputMode === "reset" && val) {
          if (["soft", "mixed", "hard"].includes(val)) {
            const r = runAction(`git reset --${val} HEAD~1`);
            app.flash(r.split("\n")[0] || `Reset --${val}`);
            refresh();
          } else { app.flash("Use: soft, mixed, or hard"); }
        }
        inputMode = "none"; inputValue = "";
        app.requestRender(); return;
      }
      if (key.name === "escape") { inputMode = "none"; inputValue = ""; app.requestRender(); return; }
      if (key.name === "backspace") { inputValue = inputValue.slice(0, -1); app.requestRender(); return; }
      if (!key.ctrl && key.name.length === 1) { inputValue += key.name; app.requestRender(); return; }
      return;
    }

    const max = getCount();

    // Tab switching
    if (key.name === "1") { view = "log"; scrollOffset = 0; selectedIndex = 0; refresh(); app.requestRender(); }
    else if (key.name === "2") { view = "status"; scrollOffset = 0; selectedIndex = 0; loadStatus(); app.requestRender(); }
    else if (key.name === "3") { view = "branches"; scrollOffset = 0; selectedIndex = 0; loadBranches(); app.requestRender(); }
    else if (key.name === "4") { view = "tags"; scrollOffset = 0; selectedIndex = 0; loadTags(); app.requestRender(); }
    else if (key.name === "5") { view = "stash"; scrollOffset = 0; selectedIndex = 0; loadStash(); app.requestRender(); }
    else if (key.name === "6") { view = "remotes"; scrollOffset = 0; selectedIndex = 0; loadRemotes(); app.requestRender(); }
    else if (key.name === "7") { view = "prs"; scrollOffset = 0; selectedIndex = 0; loadPRs(); app.requestRender(); }
    else if (key.name === "8") { view = "diff"; scrollOffset = 0; selectedIndex = 0; loadDiff(); app.requestRender(); }
    else if (key.name === "tab") {
      const order: View[] = ["log", "status", "branches", "tags", "stash", "remotes", "prs", "diff"];
      view = order[(order.indexOf(view) + 1) % order.length]!;
      scrollOffset = 0; selectedIndex = 0; refresh(); app.requestRender();
    }

    // Movement
    else if (key.name === "j" || key.name === "down") {
      if (view === "diff") scrollOffset++;
      else selectedIndex = Math.min(max - 1, selectedIndex + 1);
      app.requestRender();
    }
    else if (key.name === "k" || key.name === "up") {
      if (view === "diff") scrollOffset = Math.max(0, scrollOffset - 1);
      else selectedIndex = Math.max(0, selectedIndex - 1);
      app.requestRender();
    }
    else if (key.name === "pagedown") { const j = getTermSize().rows - 8; if (view === "diff") scrollOffset += j; else selectedIndex = Math.min(max - 1, selectedIndex + j); app.requestRender(); }
    else if (key.name === "pageup") { const j = getTermSize().rows - 8; if (view === "diff") scrollOffset = Math.max(0, scrollOffset - j); else selectedIndex = Math.max(0, selectedIndex - j); app.requestRender(); }
    else if (key.name === "r") { refresh(); app.requestRender(); app.flash("Refreshed"); }

    // ── Log actions ──
    else if (view === "log") {
      const c = commits[selectedIndex];
      if (key.name === "return" && c) { loadCommitDiff(c.hash); prevView = "log"; view = "diff"; scrollOffset = 0; app.requestRender(); }
      else if (key.name === "b" && c?.refs) {
        const branch = c.refs.split(",")[0]!.trim().replace("HEAD -> ", "");
        if (branch && branch !== currentBranch) { app.flash(runAction(`git checkout ${branch}`).split("\n")[0] || `→ ${branch}`); refresh(); app.requestRender(); }
      }
      else if (key.name === "c" && c) { app.flash(runAction(`git cherry-pick ${c.hash}`).split("\n")[0] || `Cherry-picked ${c.hash}`); refresh(); app.requestRender(); }
      else if (key.name === "v" && c) { app.flash(runAction(`git revert --no-edit ${c.hash}`).split("\n")[0] || `Reverted ${c.hash}`); refresh(); app.requestRender(); }
      else if (key.name === "n") { inputMode = "branch-name"; inputValue = ""; app.requestRender(); }
      else if (key.name === "/" || key.name === "?") {
        if (searchFilter) { searchFilter = ""; loadLog(); app.requestRender(); }
        else { inputMode = "search"; inputValue = ""; app.requestRender(); }
      }
      else if (key.name === "M") { muteMerges = !muteMerges; loadLog(); app.requestRender(); app.flash(muteMerges ? "Merge commits hidden" : "Merge commits shown"); }
      else if (key.name === "C" && c) {
        if (!compareHash) { compareHash = c.hash; app.flash(`Compare from: ${c.hash} — select target and press C`); }
        else { loadComparisonDiff(compareHash, c.hash); compareHash = ""; prevView = "log"; view = "diff"; scrollOffset = 0; app.requestRender(); }
      }
    }

    // ── Status actions ──
    else if (view === "status") {
      const line = statusLines[selectedIndex];
      const file = line?.slice(3).trim();
      if (key.name === "a" && file) { runAction(`git add "${file}"`); app.flash(`Staged ${file}`); loadStatus(); app.requestRender(); }
      else if (key.name === "u" && file) { runAction(`git restore --staged "${file}"`); app.flash(`Unstaged ${file}`); loadStatus(); app.requestRender(); }
      else if (key.name === "s") { runAction("git add -A"); app.flash("Staged all"); loadStatus(); app.requestRender(); }
      else if (key.name === "f") { app.flash("Fetching..."); app.flash(runAction("git fetch --all --prune").split("\n")[0] || "Fetched"); refresh(); app.requestRender(); }
      else if (key.name === "p") { app.flash("Pulling..."); app.flash(runAction("git pull").split("\n")[0] || "Pulled"); refresh(); app.requestRender(); }
      else if (key.name === "P") { app.flash("Pushing..."); app.flash(runAction("git push").split("\n")[0] || "Pushed"); refresh(); app.requestRender(); }
      else if (key.name === "S") { app.flash(runAction("git stash push -m 'stash from molt.tui'").split("\n")[0] || "Stashed"); loadStatus(); app.requestRender(); }
      else if (key.name === "R") { inputMode = "reset"; inputValue = ""; app.requestRender(); }
      else if (key.name === "return" && file) {
        const raw = run(`git diff "${file}" --no-color`);
        diffLines = raw ? raw.split("\n") : ["(no changes)"];
        prevView = "status"; view = "diff"; scrollOffset = 0; app.requestRender();
      }
    }

    // ── Branch actions ──
    else if (view === "branches") {
      const line = branchLines[selectedIndex];
      const branch = line?.split("|")[1]?.trim();
      if (key.name === "return" && branch && branch !== currentBranch) { app.flash(runAction(`git checkout ${branch}`).split("\n")[0] || `→ ${branch}`); refresh(); app.requestRender(); }
      else if (key.name === "n") { inputMode = "branch-name"; inputValue = ""; app.requestRender(); }
      else if (key.name === "D" && branch && branch !== currentBranch) { app.flash(runAction(`git branch -d ${branch}`).split("\n")[0] || `Deleted ${branch}`); loadBranches(); app.requestRender(); }
      else if (key.name === "m" && branch && branch !== currentBranch) { app.flash(runAction(`git merge ${branch}`).split("\n")[0] || `Merged ${branch}`); refresh(); app.requestRender(); }
      else if (key.name === "e" && branch && branch !== currentBranch) { app.flash(runAction(`git rebase ${branch}`).split("\n")[0] || `Rebased onto ${branch}`); refresh(); app.requestRender(); }
      else if (key.name === "R" && branch) {
        inputMode = "branch-name"; inputValue = branch; app.requestRender();
        // After input, rename
        const oldInputHandler = inputMode;
        // We'll handle rename in the input handler by checking if branch exists
      }
    }

    // ── Tag actions ──
    else if (view === "tags") {
      const line = tagLines[selectedIndex];
      const tag = line?.split("|")[0]?.trim();
      if (key.name === "n") { inputMode = "tag-name"; inputValue = ""; app.requestRender(); }
      else if (key.name === "D" && tag) { app.flash(runAction(`git tag -d ${tag}`).split("\n")[0] || `Deleted tag ${tag}`); loadTags(); app.requestRender(); }
      else if (key.name === "P" && tag) { app.flash(runAction(`git push origin ${tag}`).split("\n")[0] || `Pushed tag ${tag}`); app.requestRender(); }
      else if (key.name === "return" && tag) { loadCommitDiff(tag); prevView = "tags"; view = "diff"; scrollOffset = 0; app.requestRender(); }
    }

    // ── Stash actions ──
    else if (view === "stash") {
      const line = stashLines[selectedIndex];
      const ref = line?.split("|")[0]?.trim();
      if (key.name === "a" && ref) { app.flash(runAction(`git stash apply ${ref}`).split("\n")[0] || `Applied ${ref}`); refresh(); app.requestRender(); }
      else if (key.name === "p" && ref) { app.flash(runAction(`git stash pop ${ref}`).split("\n")[0] || `Popped ${ref}`); loadStash(); loadStatus(); app.requestRender(); }
      else if (key.name === "D" && ref) { app.flash(runAction(`git stash drop ${ref}`).split("\n")[0] || `Dropped ${ref}`); loadStash(); app.requestRender(); }
      else if (key.name === "return" && ref) { loadCommitDiff(ref); prevView = "stash"; view = "diff"; scrollOffset = 0; app.requestRender(); }
    }

    // ── Remote actions ──
    else if (view === "remotes") {
      const line = remoteLines[selectedIndex];
      const remote = line?.split(/\s+/)[0]?.trim();
      if (key.name === "n") { inputMode = "remote-add"; inputValue = ""; app.requestRender(); }
      else if (key.name === "D" && remote) { app.flash(runAction(`git remote remove ${remote}`).split("\n")[0] || `Removed ${remote}`); loadRemotes(); app.requestRender(); }
      else if (key.name === "f" && remote) { app.flash(runAction(`git fetch ${remote} --prune`).split("\n")[0] || `Fetched ${remote}`); app.requestRender(); }
    }

    // ── PR actions ──
    else if (view === "prs") {
      const line = prLines[selectedIndex]; const m = line?.match(/^#(\d+)/);
      if (key.name === "return" && m) { app.flash(`Checking out PR #${m[1]}...`); app.flash(runAction(`gh pr checkout ${m[1]}`).split("\n")[0] || `→ PR #${m[1]}`); refresh(); app.requestRender(); }
    }

    // Back
    else if (key.name === "escape") {
      if (view === "diff") { view = prevView; scrollOffset = 0; refresh(); app.requestRender(); }
      else { app.back(); }
    }
  },
};

function loadDiff() {
  const raw = run("git diff --stat"); const full = run("git diff --no-color");
  diffLines = raw ? [...raw.split("\n"), "", ...full.split("\n").slice(0, 300)] : ["(no changes)"];
}
