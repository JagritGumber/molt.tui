// Feed screen - browse Moltbook posts

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawHR, drawSpinner, badge } from "../tui/components.ts";
import { MoltbookClient, type MoltbookPost } from "../clients/moltbook.ts";
import { loadConfig } from "../utils/config.ts";
import type { KeyEvent } from "../tui/input.ts";

let posts: MoltbookPost[] = [];
let selectedPost = 0;
let loading = false;
let error = "";
let scrollOffset = 0;

async function fetchPosts() {
  const config = loadConfig();
  if (!config.moltbookApiKey) {
    error = "Moltbook API key not configured";
    return;
  }

  loading = true;
  error = "";
  app.requestRender();

  try {
    const client = new MoltbookClient(config.moltbookApiKey);
    posts = await client.getPosts(undefined, 25);
  } catch (err: any) {
    error = err.message || "Failed to fetch posts";
    posts = [];
  }

  loading = false;
  app.requestRender();
}

export const feedScreen: Screen = {
  name: "feed",
  statusHint: "↑↓ navigate • r refresh • esc back",

  onEnter() {
    posts = [];
    selectedPost = 0;
    scrollOffset = 0;
    fetchPosts();
  },

  render() {
    const { rows, cols } = getTermSize();
    const w = Math.min(80, cols - 4);

    cursor.to(3, 3);
    write(`${fg.brightCyan}${style.bold}Moltbook Feed${style.reset}  ${fg.gray}(${posts.length} posts)${style.reset}`);
    drawHR(4, 3, w);

    if (loading) {
      drawSpinner(6, 5, "Loading feed...");
      return;
    }

    if (error) {
      cursor.to(6, 5);
      write(`${fg.brightRed}${error}${style.reset}`);
      return;
    }

    if (posts.length === 0) {
      cursor.to(6, 5);
      write(`${fg.gray}No posts found.${style.reset}`);
      return;
    }

    const maxVisible = Math.floor((rows - 7) / 4);
    const start = Math.max(0, Math.min(scrollOffset, posts.length - maxVisible));

    for (let i = 0; i < maxVisible && start + i < posts.length; i++) {
      const idx = start + i;
      const post = posts[idx]!;
      const row = 5 + i * 4;
      const isSelected = idx === selectedPost;
      const prefix = isSelected ? `${fg.brightCyan}❯ ` : "  ";

      cursor.to(row, 3);
      write(`${prefix}${isSelected ? style.bold : ""}${fg.brightWhite}${post.title}${style.reset}`);

      cursor.to(row + 1, 5);
      const preview = post.content.slice(0, Math.min(w - 8, 120)).replace(/\n/g, " ");
      write(`${fg.gray}${preview}${post.content.length > 120 ? "…" : ""}${style.reset}`);

      cursor.to(row + 2, 5);
      write(`${badge(post.submolt || "general", fg.cyan)}  ${fg.gray}↑${post.upvotes ?? 0}${style.reset}`);
    }
  },

  onKey(key: KeyEvent) {
    if (key.name === "escape") {
      app.back();
    } else if (key.name === "up" || key.name === "k") {
      selectedPost = Math.max(0, selectedPost - 1);
      const { rows } = getTermSize();
      const maxVisible = Math.floor((rows - 7) / 4);
      if (selectedPost < scrollOffset) scrollOffset = selectedPost;
      app.requestRender();
    } else if (key.name === "down" || key.name === "j") {
      selectedPost = Math.min(posts.length - 1, selectedPost + 1);
      const { rows } = getTermSize();
      const maxVisible = Math.floor((rows - 7) / 4);
      if (selectedPost >= scrollOffset + maxVisible) scrollOffset = selectedPost - maxVisible + 1;
      app.requestRender();
    } else if (key.name === "r") {
      fetchPosts();
    }
  },
};
