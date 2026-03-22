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
  clear: () => {
    // Clear entire screen + move home + clear scrollback
    write(`${ESC}2J${ESC}H${ESC}3J`);
  },
  clearLine: () => write(`${ESC}2K`),
  clearToEOL: () => write(`${ESC}K`),
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

// Terminal column width of a single character
// Wide chars (CJK, emoji, some symbols) occupy 2 columns
function charWidth(cp: number): number {
  // Surrogate halves (handled by codePointAt in caller)
  if (cp < 0x20) return 0;
  // Fast path: ASCII
  if (cp < 0x7F) return 1;
  // Zero-width characters
  if (
    (cp >= 0x0300 && cp <= 0x036F) || // combining diacriticals
    (cp >= 0xFE00 && cp <= 0xFE0F) || // variation selectors
    (cp >= 0x200B && cp <= 0x200F) || // zero-width spaces
    (cp >= 0x2028 && cp <= 0x202F) || // line/paragraph separators
    (cp >= 0xE0100 && cp <= 0xE01EF) || // variation selectors supplement
    cp === 0xFEFF // BOM
  ) return 0;
  // Wide characters: CJK, fullwidth, emoji, ambiguous-width symbols
  if (
    (cp >= 0x1100 && cp <= 0x115F) || // Hangul Jamo
    (cp >= 0x25A0 && cp <= 0x25FF) || // Geometric Shapes (▸, ◑, etc.) — ambiguous width
    (cp >= 0x2600 && cp <= 0x26FF) || // Miscellaneous Symbols (★, etc.)
    (cp >= 0x2700 && cp <= 0x27BF) || // Dingbats (✓, ✗, etc.)
    (cp >= 0x2E80 && cp <= 0x303E) || // CJK radicals, ideographic desc
    (cp >= 0x3041 && cp <= 0x33BF) || // Hiragana, Katakana, CJK compat
    (cp >= 0x3400 && cp <= 0x4DBF) || // CJK Unified ext A
    (cp >= 0x4E00 && cp <= 0xA4CF) || // CJK Unified, Yi
    (cp >= 0xAC00 && cp <= 0xD7AF) || // Hangul syllables
    (cp >= 0xF900 && cp <= 0xFAFF) || // CJK compat ideographs
    (cp >= 0xFE30 && cp <= 0xFE6F) || // CJK compat forms, small variants
    (cp >= 0xFF01 && cp <= 0xFF60) || // Fullwidth forms
    (cp >= 0xFFE0 && cp <= 0xFFE6) || // Fullwidth signs
    (cp >= 0x1F000 && cp <= 0x1FFFF) || // Emoji & symbols (Mahjong, playing cards, emoticons, etc.)
    (cp >= 0x20000 && cp <= 0x2FFFF) || // CJK Unified ext B-F
    (cp >= 0x30000 && cp <= 0x3FFFF)    // CJK Unified ext G+
  ) return 2;
  return 1;
}

// Count terminal columns (not JS string length) for visible text
export function termWidth(str: string): number {
  let w = 0;
  for (let i = 0; i < str.length; ) {
    const cp = str.codePointAt(i)!;
    w += charWidth(cp);
    i += cp > 0xFFFF ? 2 : 1; // skip surrogate pair
  }
  return w;
}

export function visibleLength(str: string): number {
  return termWidth(stripAnsi(str));
}

// Pad/truncate to exact visible width (terminal columns)
export function fitWidth(str: string, width: number): string {
  const vw = visibleLength(str);
  if (vw > width) {
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
        const cp = chars[i]!.codePointAt(0)!;
        const cw = cp < 0x7F ? 1 : (termWidth(chars[i]!));
        if (count + cw > width - 1) break;
        result += chars[i];
        count += cw;
        i++;
      }
    }
    return result + "…" + style.reset;
  }
  return str + " ".repeat(width - vw);
}
