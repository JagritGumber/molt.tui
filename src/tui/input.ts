// Raw keyboard input handling for TUI
// Parses ANSI escape sequences into structured key events

export interface KeyEvent {
  name: string;
  ctrl: boolean;
  shift: boolean;
  alt: boolean;
  raw: string;
}

type KeyHandler = (key: KeyEvent) => void;

let currentHandler: KeyHandler | null = null;
let rawMode = false;

export function startInput(handler: KeyHandler) {
  currentHandler = handler;
  if (!rawMode && process.stdin.isTTY) {
    try {
      process.stdin.setRawMode(true);
      rawMode = true;
    } catch {
      // EPERM on some WSL/tmux combos — fall back to line mode
      rawMode = false;
    }
  }
  process.stdin.resume();
  process.stdin.setEncoding("utf-8");
  process.stdin.on("data", onData);
}

export function stopInput() {
  process.stdin.removeListener("data", onData);
  process.stdin.pause();
  if (rawMode && process.stdin.isTTY) {
    process.stdin.setRawMode(false);
    rawMode = false;
  }
  currentHandler = null;
}

function onData(data: string) {
  if (!currentHandler) return;

  // Parse each character/sequence
  let i = 0;
  while (i < data.length) {
    const key = parseKey(data, i);
    i += key.raw.length;
    currentHandler(key);
  }
}

function parseKey(data: string, offset: number): KeyEvent {
  const ch = data[offset]!;
  const rest = data.slice(offset);

  // Ctrl+C
  if (ch === "\x03") return { name: "c", ctrl: true, shift: false, alt: false, raw: ch };
  // Ctrl+D
  if (ch === "\x04") return { name: "d", ctrl: true, shift: false, alt: false, raw: ch };
  // Enter
  if (ch === "\r" || ch === "\n") return { name: "return", ctrl: false, shift: false, alt: false, raw: ch };
  // Tab
  if (ch === "\t") return { name: "tab", ctrl: false, shift: false, alt: false, raw: ch };
  // Backspace
  if (ch === "\x7f" || ch === "\b") return { name: "backspace", ctrl: false, shift: false, alt: false, raw: ch };
  // Escape sequences
  if (ch === "\x1b") {
    if (rest.startsWith("\x1b[A")) return { name: "up", ctrl: false, shift: false, alt: false, raw: "\x1b[A" };
    if (rest.startsWith("\x1b[B")) return { name: "down", ctrl: false, shift: false, alt: false, raw: "\x1b[B" };
    if (rest.startsWith("\x1b[C")) return { name: "right", ctrl: false, shift: false, alt: false, raw: "\x1b[C" };
    if (rest.startsWith("\x1b[D")) return { name: "left", ctrl: false, shift: false, alt: false, raw: "\x1b[D" };
    if (rest.startsWith("\x1b[H")) return { name: "home", ctrl: false, shift: false, alt: false, raw: "\x1b[H" };
    if (rest.startsWith("\x1b[F")) return { name: "end", ctrl: false, shift: false, alt: false, raw: "\x1b[F" };
    if (rest.startsWith("\x1b[3~")) return { name: "delete", ctrl: false, shift: false, alt: false, raw: "\x1b[3~" };
    if (rest.startsWith("\x1b[5~")) return { name: "pageup", ctrl: false, shift: false, alt: false, raw: "\x1b[5~" };
    if (rest.startsWith("\x1b[6~")) return { name: "pagedown", ctrl: false, shift: false, alt: false, raw: "\x1b[6~" };
    // Shift+Tab
    if (rest.startsWith("\x1b[Z")) return { name: "tab", ctrl: false, shift: true, alt: false, raw: "\x1b[Z" };
    // Just escape
    return { name: "escape", ctrl: false, shift: false, alt: false, raw: ch };
  }
  // Ctrl+letter
  if (ch.charCodeAt(0) < 27) {
    return { name: String.fromCharCode(ch.charCodeAt(0) + 96), ctrl: true, shift: false, alt: false, raw: ch };
  }
  // Regular character
  return { name: ch, ctrl: false, shift: false, alt: false, raw: ch };
}
