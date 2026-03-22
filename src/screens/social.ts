// Social screen — autonomous Moltbook agent dashboard
// Agent posts, comments, upvotes on its own. User monitors and corrects.

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, bg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawHR, getSpinnerFrame } from "../tui/components.ts";
import { listAgents, type AgentPersonality } from "../agents/personality.ts";
import { loadConfig } from "../utils/config.ts";
import { MoltbookClient } from "../clients/moltbook.ts";
import { ZaiClient, type PersonalityPrompt } from "../clients/zai.ts";
import { buildLearningPrompt, addLearning } from "../agents/learnings.ts";
import type { KeyEvent } from "../tui/input.ts";

type View = "status" | "feed" | "notifications";

let view: View = "status";
let agents: AgentPersonality[] = [];
let activeAgent: AgentPersonality | null = null;
let agentSelectIdx = 0;

// Activity log
interface ActivityEntry {
  time: string;
  action: string;
  detail: string;
  status: "ok" | "fail" | "pending";
}
let activityLog: ActivityEntry[] = [];
let activityScroll = 0;

// Agent state
let isRunning = false;
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
let lastCheck = "";
let homeData: any = null;

// Feed view
let feedPosts: any[] = [];
let feedIdx = 0;
let feedSort: "hot" | "new" | "top" = "hot";
let feedLoading = false;

// Notifications view
let notifications: any[] = [];
let notifIdx = 0;
let notifLoading = false;

// Compose/review
let draftPost = "";
let draftTitle = "";

// Dedup: track comment IDs we've already replied to
const repliedCommentIds = new Set<string>();
// Dedup: track post IDs we've already engaged with
const engagedPostIds = new Set<string>();

// ── Helpers ──

function getAuthorName(obj: any): string {
  // Moltbook API nests author as { author: { name: "..." } }
  if (obj?.author?.name) return obj.author.name;
  if (obj?.author_name) return obj.author_name;
  if (typeof obj?.author === "string") return obj.author;
  return "unknown";
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}

function log(action: string, detail: string, status: ActivityEntry["status"] = "ok") {
  activityLog.unshift({
    time: new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit" }),
    action,
    detail: detail.replace(/[\n\r]/g, " ").slice(0, 60),
    status,
  });
  if (activityLog.length > 100) activityLog.length = 100;
  app.requestRender();
}

function getClient(): MoltbookClient | null {
  const config = loadConfig();
  if (!config.moltbookApiKey) return null;
  return new MoltbookClient(config.moltbookApiKey);
}

function getZai(): ZaiClient | null {
  const config = loadConfig();
  if (!config.zaiApiKey) return null;
  return new ZaiClient(config.zaiApiKey, config.zaiModel);
}

function getPersonality(): PersonalityPrompt | null {
  if (!activeAgent) return null;
  const learnings = buildLearningPrompt(activeAgent.id);
  return {
    name: activeAgent.name,
    tone: activeAgent.tone,
    topics: activeAgent.topics,
    style: activeAgent.style,
    bio: activeAgent.bio,
    constraints: activeAgent.constraints,
    learnings,
  };
}

// ── Autonomous agent actions ──

async function checkHome() {
  const client = getClient();
  if (!client) { log("home", "no API key", "fail"); return; }
  try {
    homeData = await client.getHome();
    lastCheck = new Date().toLocaleTimeString("en-US", { hour12: false });
    const notifs = homeData?.your_account?.unread_notification_count || 0;
    log("home", `checked — ${notifs} notifications`);

    // Auto-engage: reply to comments on our posts
    if (homeData?.activity_on_your_posts?.length > 0) {
      for (const activity of homeData.activity_on_your_posts.slice(0, 3)) {
        await autoReply(activity);
      }
    }

    // Mark notifications read after processing
    if (notifs > 0) {
      try { await client.markAllRead(); } catch {}
    }
  } catch (err: any) {
    log("home", err.message?.slice(0, 50) || "failed", "fail");
  }
}

async function autoReply(activity: any) {
  const zai = getZai();
  const client = getClient();
  const persona = getPersonality();
  if (!zai || !client || !persona) return;

  try {
    const comments = await client.getComments(activity.post_id, "new");
    const recentComments = comments?.comments?.slice(0, 3) || [];

    for (const comment of recentComments) {
      const authorName = getAuthorName(comment);
      if (authorName === activeAgent?.name) continue;
      if (repliedCommentIds.has(comment.id)) continue;
      repliedCommentIds.add(comment.id);

      const reply = await zai.chatCompletion([
        { role: "system", content: `You are ${persona.name}. ${persona.tone}. Reply to a comment on your Moltbook post. Be brief (1-2 sentences), authentic, and in character. Just the reply text, nothing else.${persona.learnings || ""}` },
        { role: "user", content: `Post: "${activity.post_title}"\nComment by ${authorName}: "${comment.content}"\n\nReply:` },
      ], { maxTokens: 150 });
      await client.addComment(activity.post_id, reply, comment.id);
      log("reply", `→ ${authorName}: ${reply.slice(0, 40)}`);
    }
  } catch (err: any) {
    log("reply", err.message?.slice(0, 50) || "failed", "fail");
  }
}

async function autoPost() {
  const zai = getZai();
  const client = getClient();
  const persona = getPersonality();
  if (!zai || !client || !persona) { log("post", "missing config", "fail"); return; }

  try {
    log("post", "generating...", "pending");
    draftPost = await zai.generatePost(persona);
    draftTitle = await zai.generatePostTitle(draftPost);
    log("post", `draft: "${draftTitle.slice(0, 40)}"`, "pending");

    const result = await client.createPost({
      submolt_name: activeAgent?.submolts[0] || "general",
      title: draftTitle,
      content: draftPost,
    });

    if (result?.verification_required && result?.post?.verification) {
      await handleVerification(client, result.post.verification);
    }

    log("post", `published: "${draftTitle.slice(0, 40)}"`);
  } catch (err: any) {
    log("post", err.message?.slice(0, 50) || "failed", "fail");
  }
}

async function handleVerification(client: MoltbookClient, verification: any) {
  const zai = getZai();
  if (!zai) return;

  try {
    const challenge = verification.challenge_text;
    const answer = await zai.chatCompletion([
      { role: "system", content: "You solve obfuscated math word problems. Read through scattered symbols, alternating caps, and broken words to find the math problem. Respond with ONLY the numeric answer with 2 decimal places (e.g., '15.00'). Nothing else." },
      { role: "user", content: challenge },
    ], { maxTokens: 20 });

    await client.verify(verification.verification_code, answer.trim());
    log("verify", `solved challenge: ${answer.trim()}`);
  } catch (err: any) {
    log("verify", err.message?.slice(0, 50) || "failed", "fail");
  }
}

async function autoEngage() {
  const client = getClient();
  const zai = getZai();
  const persona = getPersonality();
  if (!client || !zai || !persona) return;

  try {
    const feed = await client.getFeed("hot", 15);
    const posts = feed?.posts || feed?.data || [];
    if (posts.length === 0) return;

    // Pick a post we haven't engaged with yet
    const candidates = posts.filter((p: any) => !engagedPostIds.has(p.id));
    const post = candidates[Math.floor(Math.random() * Math.min(5, candidates.length))];
    if (!post) return;
    engagedPostIds.add(post.id);

    // Keep dedup set bounded
    if (engagedPostIds.size > 200) {
      const arr = [...engagedPostIds];
      engagedPostIds.clear();
      for (const id of arr.slice(-100)) engagedPostIds.add(id);
    }

    // Upvote
    try {
      await client.upvote(post.id);
      const author = getAuthorName(post);
      log("upvote", `↑ ${author}: "${(post.title || "").slice(0, 35)}"`);
    } catch {}

    // Comment (30% chance)
    if (Math.random() < 0.3) {
      const author = getAuthorName(post);
      const comment = await zai.chatCompletion([
        { role: "system", content: `You are ${persona.name}. ${persona.tone}. Comment on a Moltbook post. Be brief (1-2 sentences), genuine, add value. Just the comment text.${persona.learnings || ""}` },
        { role: "user", content: `Post by ${author}: "${post.title}"\n${(post.content || "").slice(0, 300)}\n\nYour comment:` },
      ], { maxTokens: 150 });
      await client.addComment(post.id, comment);
      log("comment", `on "${(post.title || "").slice(0, 30)}": ${comment.slice(0, 30)}`);
    }
  } catch (err: any) {
    log("engage", err.message?.slice(0, 50) || "failed", "fail");
  }
}

// ── Feed & Notifications ──

async function loadFeed() {
  const client = getClient();
  if (!client || feedLoading) return;
  feedLoading = true;
  try {
    const result = await client.getFeed(feedSort, 25);
    feedPosts = result?.posts || result?.data || [];
    feedIdx = 0;
    log("feed", `loaded ${feedPosts.length} posts (${feedSort})`);
  } catch (err: any) {
    log("feed", err.message?.slice(0, 50) || "failed", "fail");
  }
  feedLoading = false;
  app.requestRender();
}

async function loadNotifications() {
  const client = getClient();
  if (!client || notifLoading) return;
  notifLoading = true;
  try {
    // Use home data's activity_on_your_posts as notifications
    if (!homeData) {
      homeData = await client.getHome();
    }
    notifications = homeData?.activity_on_your_posts || [];
    notifIdx = 0;
    log("notif", `loaded ${notifications.length} activities`);
  } catch (err: any) {
    log("notif", err.message?.slice(0, 50) || "failed", "fail");
  }
  notifLoading = false;
  app.requestRender();
}

// ── Agent control ──

function startAgent() {
  if (isRunning || !activeAgent) return;
  isRunning = true;
  log("agent", `started: ${activeAgent.name}`);

  checkHome();

  // Heartbeat: check home every 5 min, engage every 10 min, post every 30 min
  let tickCount = 0;
  heartbeatTimer = setInterval(() => {
    tickCount++;
    checkHome();
    if (tickCount % 2 === 0) autoEngage();
    if (tickCount % 6 === 0) autoPost();
  }, 5 * 60 * 1000);

  app.requestRender();
}

function stopAgent() {
  if (!isRunning) return;
  isRunning = false;
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
  log("agent", "stopped");
  app.requestRender();
}

// ── Rendering ──

const ACTION_COLORS: Record<string, string> = {
  post: fg.brightMagenta,
  reply: fg.brightCyan,
  comment: fg.brightBlue,
  upvote: fg.brightGreen,
  engage: fg.brightYellow,
  home: fg.gray,
  agent: fg.brightWhite,
  verify: fg.brightYellow,
  feed: fg.brightBlue,
  notif: fg.brightYellow,
  follow: fg.brightGreen,
};

function renderStatus() {
  const { rows, cols } = getTermSize();
  const w = Math.min(75, cols - 4);

  let row = 2;

  // Header
  cursor.to(row, 3);
  write(`${fg.brightCyan}${style.bold}Social${style.reset}`);
  cursor.to(row, 12);
  if (activeAgent) {
    const status = isRunning ? `${fg.brightGreen}● running` : `${fg.gray}○ stopped`;
    write(`${fg.brightWhite}${style.bold}${activeAgent.name}${style.reset} ${status}${style.reset}\x1b[K`);
  } else {
    write(`${fg.gray}no agent selected\x1b[K${style.reset}`);
  }
  row++;
  drawHR(row, 3, w); row++;

  // Stats row
  cursor.to(row, 3);
  if (homeData?.your_account) {
    const acc = homeData.your_account;
    const karma = acc.karma || 0;
    const notifs = acc.unread_notification_count || 0;
    const karmaColor = karma > 10 ? fg.brightGreen : karma > 0 ? fg.brightWhite : fg.gray;
    write(`${fg.gray}Karma: ${karmaColor}${karma}${fg.gray}  Notifs: ${notifs > 0 ? fg.brightYellow : fg.gray}${notifs}${fg.gray}  Last: ${fg.white}${lastCheck || "—"}${style.reset}\x1b[K`);
  } else {
    write(`${fg.gray}No data — press ${fg.brightWhite}S${fg.gray} to start or ${fg.brightWhite}H${fg.gray} to check${style.reset}\x1b[K`);
  }
  row++; row++;

  // Tab bar
  cursor.to(row, 3);
  const tabs = [
    view === "status" ? `${bg.rgb(50, 50, 80)}${fg.brightWhite}${style.bold} Activity ` : `${fg.gray} Activity `,
    view === "feed" ? `${bg.rgb(50, 50, 80)}${fg.brightWhite}${style.bold} Feed ` : `${fg.gray} Feed `,
    view === "notifications" ? `${bg.rgb(50, 50, 80)}${fg.brightWhite}${style.bold} Notifs ` : `${fg.gray} Notifs `,
  ];
  write(tabs.join(`${style.reset}${fg.gray}│`) + style.reset + "\x1b[K");
  row++;

  // Controls
  cursor.to(row, 3);
  const controls = [
    isRunning ? `${fg.brightRed}[S]${fg.gray}stop` : `${fg.brightGreen}[S]${fg.gray}start`,
    `${fg.brightCyan}[P]${fg.gray}post`,
    `${fg.brightCyan}[E]${fg.gray}engage`,
    `${fg.brightCyan}[H]${fg.gray}home`,
    `${fg.brightCyan}[1-3]${fg.gray}tabs`,
  ];
  write(controls.join("  ") + style.reset + "\x1b[K");
  row++;
  drawHR(row, 3, w); row++;

  if (view === "status") {
    renderActivityLog(row, rows, w);
  } else if (view === "feed") {
    renderFeed(row, rows, w);
  } else if (view === "notifications") {
    renderNotifications(row, rows, w);
  }
}

function renderActivityLog(startRow: number, maxRows: number, w: number) {
  const maxLines = maxRows - startRow - 2;
  for (let i = 0; i < maxLines; i++) {
    const idx = activityScroll + i;
    cursor.to(startRow + i, 3);
    if (idx >= activityLog.length) {
      write("\x1b[K");
      continue;
    }
    const entry = activityLog[idx]!;
    const icon = entry.status === "ok" ? `${fg.brightGreen}✓` : entry.status === "fail" ? `${fg.brightRed}✗` : `${fg.brightYellow}◑`;
    const color = ACTION_COLORS[entry.action] || fg.gray;
    const detail = entry.detail.slice(0, w - 18);
    write(`${fg.gray}${entry.time} ${icon} ${color}${entry.action.padEnd(8)}${fg.white}${detail}${style.reset}\x1b[K`);
  }
}

function renderFeed(startRow: number, maxRows: number, w: number) {
  if (feedLoading) {
    cursor.to(startRow, 3);
    write(`${fg.brightYellow}${getSpinnerFrame()} Loading feed...${style.reset}\x1b[K`);
    return;
  }
  if (feedPosts.length === 0) {
    cursor.to(startRow, 3);
    write(`${fg.gray}No posts — press ${fg.brightWhite}R${fg.gray} to refresh${style.reset}\x1b[K`);
    return;
  }

  cursor.to(startRow, 3);
  write(`${fg.gray}${feedSort.toUpperCase()} feed — ${feedPosts.length} posts  ${fg.brightWhite}[T]${fg.gray}sort  [R]refresh${style.reset}\x1b[K`);

  const maxLines = maxRows - startRow - 3;
  const postsToShow = Math.floor(maxLines / 3);

  for (let i = 0; i < postsToShow; i++) {
    const postIdx = feedIdx + i;
    if (postIdx >= feedPosts.length) {
      // Clear remaining lines
      for (let j = 0; j < 3; j++) {
        cursor.to(startRow + 1 + i * 3 + j, 3);
        write("\x1b[K");
      }
      continue;
    }
    const post = feedPosts[postIdx]!;
    const author = getAuthorName(post);
    const selected = i === 0; // first visible is "selected"
    const row = startRow + 1 + i * 3;

    // Title line
    cursor.to(row, 3);
    const marker = postIdx === feedIdx ? `${fg.brightCyan}▸ ` : "  ";
    const title = (post.title || "untitled").slice(0, w - 20);
    write(`${marker}${fg.brightWhite}${style.bold}${title}${style.reset}\x1b[K`);

    // Meta line
    cursor.to(row + 1, 5);
    const up = post.upvotes ?? 0;
    const comments = post.comment_count ?? 0;
    const age = post.created_at ? timeAgo(post.created_at) : "";
    const submolt = post.submolt_name ? `${fg.brightBlue}m/${post.submolt_name}` : "";
    write(`${fg.gray}${author} ${age}  ${fg.brightGreen}↑${up}${fg.gray}  💬${comments}  ${submolt}${style.reset}\x1b[K`);

    // Separator
    cursor.to(row + 2, 3);
    write(`${fg.gray}${"─".repeat(Math.min(w, 50))}${style.reset}\x1b[K`);
  }
}

function renderNotifications(startRow: number, maxRows: number, w: number) {
  if (notifLoading) {
    cursor.to(startRow, 3);
    write(`${fg.brightYellow}${getSpinnerFrame()} Loading...${style.reset}\x1b[K`);
    return;
  }
  if (notifications.length === 0) {
    cursor.to(startRow, 3);
    write(`${fg.gray}No activity — press ${fg.brightWhite}R${fg.gray} to refresh${style.reset}\x1b[K`);
    return;
  }

  const maxLines = maxRows - startRow - 2;
  for (let i = 0; i < maxLines; i++) {
    const idx = notifIdx + i;
    cursor.to(startRow + i, 3);
    if (idx >= notifications.length) {
      write("\x1b[K");
      continue;
    }
    const n = notifications[idx]!;
    const count = n.new_notification_count || 0;
    const title = (n.post_title || "untitled").slice(0, w - 30);
    const commenters = (n.latest_commenters || []).join(", ").slice(0, 20);
    const countBadge = count > 0 ? `${fg.brightYellow}(${count})` : `${fg.gray}(0)`;
    write(`${fg.brightWhite}${title} ${countBadge} ${fg.gray}by ${fg.brightCyan}${commenters || "—"}${style.reset}\x1b[K`);
  }
}

// ── Key handling ──

export const socialScreen: Screen = {
  name: "social",
  statusHint: "S start/stop • P post • E engage • H home • 1-3 tabs • esc back • q quit",

  onEnter() {
    agents = listAgents();
    if (agents.length > 0 && !activeAgent) {
      activeAgent = agents[0]!;
    }
  },

  onLeave() {
    // Don't stop the agent when leaving — it runs in background
  },

  render() {
    renderStatus();
  },

  onKey(key: KeyEvent) {
    // Navigation
    if (key.name === "escape") {
      if (view !== "status") { view = "status"; app.requestRender(); }
      else app.back();
      return;
    }

    // Tab switching
    if (key.name === "1") { view = "status"; app.requestRender(); return; }
    if (key.name === "2") {
      view = "feed";
      if (feedPosts.length === 0) loadFeed();
      app.requestRender();
      return;
    }
    if (key.name === "3") {
      view = "notifications";
      if (notifications.length === 0) loadNotifications();
      app.requestRender();
      return;
    }

    // Agent controls (work in all views)
    if (key.name === "s" || key.name === "S") {
      if (isRunning) stopAgent();
      else startAgent();
      return;
    }
    if (key.name === "p" || key.name === "P") {
      if (activeAgent) { log("post", "manual trigger...", "pending"); autoPost(); }
      return;
    }
    if (key.name === "e" || key.name === "E") {
      if (activeAgent) { log("engage", "manual trigger...", "pending"); autoEngage(); }
      return;
    }
    if (key.name === "h" || key.name === "H") {
      if (activeAgent) checkHome();
      return;
    }
    if (key.name === "tab") {
      if (agents.length > 0) {
        agentSelectIdx = (agentSelectIdx + 1) % agents.length;
        const wasRunning = isRunning;
        if (wasRunning) stopAgent();
        activeAgent = agents[agentSelectIdx]!;
        log("agent", `switched to ${activeAgent.name}`);
        if (wasRunning) startAgent();
      }
      return;
    }

    // View-specific keys
    if (view === "status") {
      if (key.name === "up" || key.name === "k") {
        activityScroll = Math.max(0, activityScroll - 1);
        app.requestRender();
      } else if (key.name === "down" || key.name === "j") {
        activityScroll = Math.min(Math.max(0, activityLog.length - 5), activityScroll + 1);
        app.requestRender();
      }
    } else if (view === "feed") {
      if (key.name === "up" || key.name === "k") {
        feedIdx = Math.max(0, feedIdx - 1);
        app.requestRender();
      } else if (key.name === "down" || key.name === "j") {
        feedIdx = Math.min(Math.max(0, feedPosts.length - 1), feedIdx + 1);
        app.requestRender();
      } else if (key.name === "r" || key.name === "R") {
        loadFeed();
      } else if (key.name === "t" || key.name === "T") {
        // Cycle sort
        const sorts: typeof feedSort[] = ["hot", "new", "top"];
        feedSort = sorts[(sorts.indexOf(feedSort) + 1) % sorts.length]!;
        loadFeed();
      }
    } else if (view === "notifications") {
      if (key.name === "up" || key.name === "k") {
        notifIdx = Math.max(0, notifIdx - 1);
        app.requestRender();
      } else if (key.name === "down" || key.name === "j") {
        notifIdx = Math.min(Math.max(0, notifications.length - 1), notifIdx + 1);
        app.requestRender();
      } else if (key.name === "r" || key.name === "R") {
        homeData = null;
        loadNotifications();
      }
    }
  },
};
