// Cheatsheet overlay — press ? from any screen to toggle

import { cursor, fg, bg, style, write, getTermSize, fitWidth } from "./ansi.ts";

interface Section {
  title: string;
  keys: [string, string][]; // [key, description]
}

const SECTIONS: Record<string, Section[]> = {
  global: [
    {
      title: "Global",
      keys: [
        ["?", "toggle this cheatsheet"],
        ["Ctrl+C", "quit"],
        ["Esc", "back / cancel"],
        ["↑/k ↓/j", "navigate up / down"],
        ["Enter", "select / confirm"],
      ],
    },
  ],
  dashboard: [
    {
      title: "Dashboard",
      keys: [
        ["s/a/t/c/q", "press key to navigate"],
      ],
    },
  ],
  social: [
    {
      title: "Social — Agent Controls",
      keys: [
        ["S", "start / stop agent"],
        ["P", "post now (manual)"],
        ["E", "engage with feed"],
        ["H", "check home / notifications"],
        ["Tab", "switch agent"],
        ["j / k", "scroll activity log"],
        ["q", "back to dashboard"],
      ],
    },
  ],
  tasks: [
    {
      title: "Tasks — Navigation",
      keys: [
        ["j / k", "move down / up"],
        ["g / G", "jump top / bottom"],
        ["Tab", "cycle filter"],
      ],
    },
    {
      title: "Tasks — Quick Actions",
      keys: [
        ["Space", "toggle status (○→◑→●)"],
        ["x", "mark done / undo"],
        ["p", "cycle priority (▽→■→▲)"],
        ["n", "new task (form)"],
        ["e", "edit selected"],
        ["d", "delete selected"],
      ],
    },
    {
      title: "Tasks — Command Bar (:)",
      keys: [
        [":add <title>", "create task"],
        ["  !high @tag", "  inline priority & tag"],
        ["  due tomorrow", "  inline due date"],
        [":done [n]", "mark task done"],
        [":wip [n]", "start task"],
        [":todo [n]", "reset to todo"],
        [":high/med/low", "set priority"],
        [":due <date>", "today/tmr/+3d/2026-04-01"],
        [":tag <t>", "add tags"],
        [":untag <t>", "remove tags"],
        [":rename <t>", "rename current task"],
        [":del [n]", "delete task"],
        [":clear done", "wipe all completed"],
        [":filter <s>", "all/todo/active/done"],
        ["↑ / ↓", "command history"],
      ],
    },
  ],
  agents: [
    {
      title: "Agents",
      keys: [
        ["↑↓ / j k", "navigate agents"],
        ["Enter", "edit agent"],
        ["n", "new agent"],
        ["d", "delete agent"],
        ["Esc / q", "back"],
      ],
    },
  ],
  settings: [
    {
      title: "Settings",
      keys: [
        ["Tab / ↓", "next field"],
        ["Shift+Tab / ↑", "prev field"],
        ["Enter", "save"],
        ["Esc", "discard & back"],
      ],
    },
  ],
  onboarding: [
    {
      title: "Onboarding",
      keys: [
        ["Tab / ↓", "next field"],
        ["Enter", "test / continue"],
        ["s", "skip (on failure)"],
        ["Esc", "go back / skip all"],
      ],
    },
  ],
  generate: [
    {
      title: "Generate Post",
      keys: [
        ["Tab / ↓", "next field"],
        ["Enter", "generate"],
        ["Esc", "back"],
      ],
    },
  ],
  post: [
    {
      title: "Post to Moltbook",
      keys: [
        ["Enter", "publish"],
        ["Esc", "back"],
      ],
    },
  ],
  feed: [
    {
      title: "Feed",
      keys: [
        ["↑↓ / j k", "scroll posts"],
        ["Enter", "view post"],
        ["r", "refresh"],
        ["Esc / q", "back"],
      ],
    },
  ],
};

let visible = false;

export function isCheatsheetVisible(): boolean {
  return visible;
}

export function toggleCheatsheet() {
  visible = !visible;
}

export function hideCheatsheet() {
  visible = false;
}

export function drawCheatsheet(activeScreen: string) {
  if (!visible) return;

  const { rows, cols } = getTermSize();

  // Collect sections: global + screen-specific
  const sections = [...(SECTIONS.global || []), ...(SECTIONS[activeScreen] || [])];

  // Calculate layout — two columns
  const totalWidth = Math.min(78, cols - 4);
  const colWidth = Math.floor((totalWidth - 3) / 2); // -3 for gap
  const startCol = Math.floor((cols - totalWidth) / 2);

  // Calculate height
  let totalLines = 2; // title + blank
  for (const s of sections) {
    totalLines += 1 + s.keys.length + 1; // section title + keys + gap
  }
  const height = Math.min(totalLines + 2, rows - 4);
  const startRow = Math.floor((rows - height) / 2);

  // Draw background
  for (let r = startRow; r < startRow + height; r++) {
    cursor.to(r, startCol);
    write(`${bg.rgb(15, 15, 30)}${" ".repeat(totalWidth)}${style.reset}`);
  }

  // Border
  cursor.to(startRow, startCol);
  write(`${bg.rgb(15, 15, 30)}${fg.cyan}┌${"─".repeat(totalWidth - 2)}┐${style.reset}`);
  for (let r = startRow + 1; r < startRow + height - 1; r++) {
    cursor.to(r, startCol);
    write(`${bg.rgb(15, 15, 30)}${fg.cyan}│${style.reset}`);
    cursor.to(r, startCol + totalWidth - 1);
    write(`${bg.rgb(15, 15, 30)}${fg.cyan}│${style.reset}`);
  }
  cursor.to(startRow + height - 1, startCol);
  write(`${bg.rgb(15, 15, 30)}${fg.cyan}└${"─".repeat(totalWidth - 2)}┘${style.reset}`);

  // Title
  cursor.to(startRow + 1, startCol + 2);
  const title = "Molt.tui Cheatsheet";
  const dismiss = "press ? to close";
  const pad = totalWidth - 4 - title.length - dismiss.length;
  write(`${bg.rgb(15, 15, 30)}${fg.brightCyan}${style.bold}${title}${style.reset}${bg.rgb(15, 15, 30)}${" ".repeat(Math.max(1, pad))}${fg.gray}${dismiss}${style.reset}`);

  // Draw sections in two columns
  const leftSections = sections.slice(0, Math.ceil(sections.length / 2));
  const rightSections = sections.slice(Math.ceil(sections.length / 2));

  let row = startRow + 3;
  const maxRow = startRow + height - 2;

  function drawColumn(secs: Section[], col: number) {
    let r = row;
    for (const sec of secs) {
      if (r >= maxRow) break;

      cursor.to(r, col);
      write(`${bg.rgb(15, 15, 30)}${fg.brightYellow}${style.bold}${sec.title}${style.reset}`);
      r++;

      for (const [key, desc] of sec.keys) {
        if (r >= maxRow) break;
        cursor.to(r, col);
        const keyStr = `${bg.rgb(15, 15, 30)}${fg.brightCyan}${style.bold}${key.padEnd(16)}${style.reset}`;
        const descStr = `${bg.rgb(15, 15, 30)}${fg.white}${desc}${style.reset}`;
        write(`${keyStr}${descStr}`);
        r++;
      }
      r++; // gap between sections
    }
  }

  drawColumn(leftSections, startCol + 2);
  drawColumn(rightSections, startCol + 2 + colWidth + 3);
}
