// Zero-dependency ANSI escape code helpers for TUI rendering
// Works everywhere: Windows Terminal, macOS Terminal, Linux, Termux on Android

export const ESC = "\x1b[";

export const cursor = {
  hide: () => write(`${ESC}?25l`),
  show: () => write(`${ESC}?25h`),
  to: (row: number, col: number) => write(`${ESC}${row};${col}H`),
  save: () => write(`${ESC}s`),
  restore: () => write(`${ESC}u`),
};

export const screen = {
  clear: () => write(`${ESC}2J${ESC}H`),
  clearLine: () => write(`${ESC}2K`),
  altBuffer: () => write(`${ESC}?1049h`),
  mainBuffer: () => write(`${ESC}?1049l`),
};

export const style = {
  reset: "\x1b[0m",
  bold: "\x1b[1m",
  dim: "\x1b[2m",
  italic: "\x1b[3m",
  underline: "\x1b[4m",
  inverse: "\x1b[7m",
  strikethrough: "\x1b[9m",
};

export const fg = {
  black: "\x1b[30m",
  red: "\x1b[31m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  blue: "\x1b[34m",
  magenta: "\x1b[35m",
  cyan: "\x1b[36m",
  white: "\x1b[37m",
  gray: "\x1b[90m",
  brightRed: "\x1b[91m",
  brightGreen: "\x1b[92m",
  brightYellow: "\x1b[93m",
  brightBlue: "\x1b[94m",
  brightMagenta: "\x1b[95m",
  brightCyan: "\x1b[96m",
  brightWhite: "\x1b[97m",
  rgb: (r: number, g: number, b: number) => `\x1b[38;2;${r};${g};${b}m`,
};

export const bg = {
  black: "\x1b[40m",
  red: "\x1b[41m",
  green: "\x1b[42m",
  yellow: "\x1b[43m",
  blue: "\x1b[44m",
  magenta: "\x1b[45m",
  cyan: "\x1b[46m",
  white: "\x1b[47m",
  gray: "\x1b[100m",
  rgb: (r: number, g: number, b: number) => `\x1b[48;2;${r};${g};${b}m`,
};

export function write(text: string) {
  process.stdout.write(text);
}

export function writeLine(text: string) {
  process.stdout.write(text + "\n");
}

export function getTermSize(): { rows: number; cols: number } {
  return {
    rows: process.stdout.rows || 24,
    cols: process.stdout.columns || 80,
  };
}

// Strip ANSI codes for length calculation
export function stripAnsi(str: string): string {
  return str.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, "");
}

export function visibleLength(str: string): number {
  return stripAnsi(str).length;
}

// Pad/truncate to exact visible width
export function fitWidth(str: string, width: number): string {
  const visible = stripAnsi(str);
  if (visible.length > width) {
    // Truncate - need to be careful with ANSI codes
    let count = 0;
    let i = 0;
    const chars = [...str];
    let result = "";
    while (i < chars.length && count < width - 1) {
      if (chars[i] === "\x1b") {
        // Skip ANSI sequence
        let seq = "";
        while (i < chars.length && !/[a-zA-Z]/.test(chars[i]!)) {
          seq += chars[i];
          i++;
        }
        seq += chars[i] || "";
        i++;
        result += seq;
      } else {
        result += chars[i];
        count++;
        i++;
      }
    }
    return result + "…" + style.reset;
  }
  return str + " ".repeat(width - visible.length);
}
