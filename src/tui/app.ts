// Core TUI application - screen management, navigation, render loop

import { cursor, screen, write, getTermSize, fg, style } from "./ansi.ts";
import { startInput, stopInput, type KeyEvent } from "./input.ts";
import { drawHeader, drawStatusBar } from "./components.ts";

export interface Screen {
  name: string;
  render: () => void;
  onKey: (key: KeyEvent) => void;
  onEnter?: () => void;
  onLeave?: () => void;
  statusHint?: string;
}

class App {
  private screens: Map<string, Screen> = new Map();
  private activeScreen: string = "";
  private history: string[] = [];
  private renderTimer: ReturnType<typeof setInterval> | null = null;
  private needsRender = true;
  private statusMessage = "";
  private statusTimeout: ReturnType<typeof setTimeout> | null = null;

  register(s: Screen) {
    this.screens.set(s.name, s);
  }

  navigate(name: string) {
    const prev = this.screens.get(this.activeScreen);
    if (prev) {
      prev.onLeave?.();
      this.history.push(this.activeScreen);
    }
    this.activeScreen = name;
    const next = this.screens.get(name);
    next?.onEnter?.();
    this.requestRender();
  }

  back() {
    const prev = this.history.pop();
    if (prev) {
      const current = this.screens.get(this.activeScreen);
      current?.onLeave?.();
      this.activeScreen = prev;
      const next = this.screens.get(prev);
      next?.onEnter?.();
      this.requestRender();
    }
  }

  flash(message: string, durationMs = 3000) {
    this.statusMessage = message;
    if (this.statusTimeout) clearTimeout(this.statusTimeout);
    this.statusTimeout = setTimeout(() => {
      this.statusMessage = "";
      this.requestRender();
    }, durationMs);
    this.requestRender();
  }

  requestRender() {
    this.needsRender = true;
  }

  private render() {
    if (!this.needsRender) return;
    this.needsRender = false;

    cursor.hide();
    screen.clear();
    drawHeader();

    const s = this.screens.get(this.activeScreen);
    if (s) {
      s.render();
      const hint = s.statusHint || "↑↓ navigate • enter select • q quit";
      const status = this.statusMessage || hint;
      drawStatusBar(status, `screen: ${s.name}`);
    }
  }

  async start(initialScreen: string) {
    screen.altBuffer();
    cursor.hide();

    this.activeScreen = initialScreen;
    const initial = this.screens.get(initialScreen);
    initial?.onEnter?.();

    startInput((key) => {
      // Global: Ctrl+C to quit
      if (key.ctrl && key.name === "c") {
        this.shutdown();
        return;
      }
      const s = this.screens.get(this.activeScreen);
      s?.onKey(key);
    });

    // Render loop at ~30fps
    this.renderTimer = setInterval(() => this.render(), 33);
    this.render();

    // Handle resize
    process.stdout.on("resize", () => this.requestRender());

    // Keep alive
    await new Promise(() => {});
  }

  shutdown() {
    if (this.renderTimer) clearInterval(this.renderTimer);
    stopInput();
    cursor.show();
    screen.mainBuffer();
    process.exit(0);
  }
}

export const app = new App();
