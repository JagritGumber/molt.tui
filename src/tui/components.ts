// Reusable TUI components - boxes, lists, text inputs, spinners, status bars

import { cursor, fg, bg, style, write, getTermSize, fitWidth, visibleLength, stripAnsi } from "./ansi.ts";

// ── Box Drawing ──

export function drawBox(row: number, col: number, width: number, height: number, title?: string) {
  const top = "┌" + (title ? `─ ${title} ` : "") + "─".repeat(Math.max(0, width - 2 - (title ? title.length + 3 : 0))) + "┐";
  const bottom = "└" + "─".repeat(width - 2) + "┘";

  cursor.to(row, col);
  write(fg.cyan + top + style.reset);

  for (let i = 1; i < height - 1; i++) {
    cursor.to(row + i, col);
    write(fg.cyan + "│" + style.reset + " ".repeat(width - 2) + fg.cyan + "│" + style.reset);
  }

  cursor.to(row + height - 1, col);
  write(fg.cyan + bottom + style.reset);
}

// ── Selectable List ──

export interface ListItem {
  label: string;
  value: string;
  description?: string;
}

export function drawList(
  row: number,
  col: number,
  width: number,
  items: ListItem[],
  selectedIndex: number,
  maxVisible: number
) {
  const scrollOffset = Math.max(0, Math.min(selectedIndex - Math.floor(maxVisible / 2), items.length - maxVisible));

  for (let i = 0; i < maxVisible; i++) {
    const idx = scrollOffset + i;
    cursor.to(row + i, col);

    if (idx >= items.length) {
      write(" ".repeat(width));
      continue;
    }

    const item = items[idx]!;
    const isSelected = idx === selectedIndex;
    const prefix = isSelected ? `${fg.brightCyan}${style.bold} ❯ ` : `   `;
    const label = isSelected
      ? `${fg.brightWhite}${style.bold}${item.label}${style.reset}`
      : `${fg.white}${item.label}${style.reset}`;
    const desc = item.description ? `  ${fg.gray}${item.description}${style.reset}` : "";

    write(fitWidth(prefix + label + desc, width));
  }

  // Scroll indicators
  if (scrollOffset > 0) {
    cursor.to(row - 1, col + width - 3);
    write(`${fg.gray}▲${style.reset}`);
  }
  if (scrollOffset + maxVisible < items.length) {
    cursor.to(row + maxVisible, col + width - 3);
    write(`${fg.gray}▼${style.reset}`);
  }
}

// ── Text Input ──

export function drawTextInput(
  row: number,
  col: number,
  width: number,
  value: string,
  label: string,
  focused: boolean,
  cursorPos?: number
) {
  cursor.to(row, col);
  const labelStr = `${fg.gray}${label}: ${style.reset}`;
  write(labelStr);

  const inputWidth = width - visibleLength(labelStr);
  const displayVal = value.length > inputWidth - 1 ? "…" + value.slice(-(inputWidth - 2)) : value;

  if (focused) {
    write(`${style.underline}${fg.brightWhite}${fitWidth(displayVal, inputWidth)}${style.reset}`);
  } else {
    write(`${fg.white}${fitWidth(displayVal || fg.gray + "(empty)", inputWidth)}${style.reset}`);
  }
}

// ── Multi-line Text Area ──

export function drawTextArea(
  row: number,
  col: number,
  width: number,
  height: number,
  lines: string[],
  scrollOffset: number,
  title?: string
) {
  if (title) {
    cursor.to(row, col);
    write(`${fg.gray}${title}${style.reset}`);
    row++;
    height--;
  }

  for (let i = 0; i < height; i++) {
    cursor.to(row + i, col);
    const lineIdx = scrollOffset + i;
    if (lineIdx < lines.length) {
      write(fitWidth(lines[lineIdx]!, width));
    } else {
      write(" ".repeat(width));
    }
  }
}

// ── Spinner ──

const SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
let spinnerIdx = 0;

export function getSpinnerFrame(): string {
  const frame = SPINNER_FRAMES[spinnerIdx % SPINNER_FRAMES.length]!;
  spinnerIdx++;
  return `${fg.brightCyan}${frame}${style.reset}`;
}

export function drawSpinner(row: number, col: number, message: string) {
  cursor.to(row, col);
  write(`${getSpinnerFrame()} ${fg.white}${message}${style.reset}`);
}

// ── Status Bar ──

export function drawStatusBar(text: string, rightText?: string) {
  const { rows, cols } = getTermSize();
  cursor.to(rows, 1);
  const left = ` ${text}`;
  const right = rightText ? `${rightText} ` : "";
  const padding = Math.max(0, cols - visibleLength(left) - visibleLength(right));

  write(`${bg.rgb(30, 30, 50)}${fg.brightWhite}${left}${" ".repeat(padding)}${fg.gray}${right}${style.reset}`);
}

// ── Header ──

export function drawHeader() {
  const { cols } = getTermSize();
  cursor.to(1, 1);
  const title = " ⚡ Molt.tui ";
  const subtitle = "agent management for moltbook";
  const padding = Math.max(0, cols - title.length - subtitle.length - 1);

  write(
    `${bg.rgb(20, 20, 40)}${fg.brightCyan}${style.bold}${title}${style.reset}` +
    `${bg.rgb(20, 20, 40)}${fg.gray} ${subtitle}${" ".repeat(padding)}${style.reset}`
  );
}

// ── Confirmation Dialog ──

export function drawDialog(title: string, message: string, options: string[]) {
  const { rows, cols } = getTermSize();
  const width = Math.min(60, cols - 4);
  const height = 7;
  const startRow = Math.floor((rows - height) / 2);
  const startCol = Math.floor((cols - width) / 2);

  drawBox(startRow, startCol, width, height, title);

  cursor.to(startRow + 2, startCol + 2);
  write(fitWidth(`${fg.white}${message}`, width - 4));

  cursor.to(startRow + 4, startCol + 2);
  write(options.map((o, i) => `${fg.brightCyan}[${o}]${style.reset}`).join("  "));
}

// ── Horizontal Rule ──

export function drawHR(row: number, col: number, width: number) {
  cursor.to(row, col);
  write(`${fg.gray}${"─".repeat(width)}${style.reset}`);
}

// ── Badge / Tag ──

export function badge(text: string, color: string = fg.brightCyan): string {
  return `${color}[${text}]${style.reset}`;
}
