// Social screen — split layout: curated feed left, activity log right
// Agent posts, comments, upvotes autonomously. User monitors, corrects, teaches.

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, bg, style, write, getTermSize, fitWidth } from "../tui/ansi.ts";
import { drawHR, getSpinnerFrame } from "../tui/components.ts";
import { listAgents, type AgentPersonality } from "../agents/personality.ts";
import { loadConfig } from "../utils/config.ts";
import { MoltbookClient } from "../clients/moltbook.ts";
import { ZaiClient, type PersonalityPrompt } from "../clients/zai.ts";
import { buildLearningPrompt, addLearning } from "../agents/learnings.ts";
import type { KeyEvent } from "../tui/input.ts";

// ── State ──

type Panel = "home" | "my-posts";

let panel: Panel = "home";
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

// Agent runtime
let isRunning = false;
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
let lastCheck = "";
let homeData: any = null;

// Feed
let feedPosts: any[] = [];
let feedIdx = 0;
let feedLoading = false;

// My posts
let myPosts: any[] = [];
let myPostIdx = 0;
let myPostsLoading = false;

// Learning input mode
let learningMode = false;
let learningInput = "";
let learningContext = ""; // post title/content that triggered learning

// Dedup
const repliedCommentIds = new Set<string>();
const engagedPostIds = new Set<string>();

// ── Helpers ──

function getAuthorName(obj: any): string {
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

function isRelevant(post: any): boolean {
  if (!activeAgent) return false;
  const topics = activeAgent.topics.map(t => t.toLowerCase());
  const text = `${post.title || ""} ${post.content || ""}`.toLowerCase();
  return topics.some(t => text.includes(t));
}

function log(action: string, detail: string, status: ActivityEntry["status"] = "ok") {
  activityLog.unshift({
    time: new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit" }),
    action,
    detail: detail.replace(/[\n\r]/g, " ").slice(0, 80),
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

// ── Data Loading ──

async function loadFeed() {
  const client = getClient();
  if (!client || feedLoading) return;
  feedLoading = true;
  app.requestRender();
  try {
    const result = await client.getFeed("hot", 25);
    feedPosts = result?.posts || result?.data || [];
    feedIdx = 0;
    log("feed", `loaded ${feedPosts.length} posts`);
  } catch (err: any) {
    log("feed", err.message?.slice(0, 50) || "failed", "fail");
  }
  feedLoading = false;
  app.requestRender();
}

async function loadMyPosts() {
  const client = getClient();
  if (!client || myPostsLoading || !activeAgent) return;
  myPostsLoading = true;
  app.requestRender();
  try {
    const profile = await client.getProfile(activeAgent.name);
    myPosts = profile?.posts || profile?.recent_posts || [];
    myPostIdx = 0;
    log("posts", `loaded ${myPosts.length} of your posts`);
  } catch (err: any) {
    // Fallback: search for agent's posts
    try {
      const result = await client.search(activeAgent.name, "posts", 20);
      myPosts = result?.posts || result?.results || [];
      myPostIdx = 0;
    } catch {
      log("posts", err.message?.slice(0, 50) || "failed", "fail");
    }
  }
  myPostsLoading = false;
  app.requestRender();
}

// ── Autonomous Agent Actions ──

async function checkHome() {
  const client = getClient();
  if (!client) { log("home", "no API key", "fail"); return; }
  try {
    homeData = await client.getHome();
    lastCheck = new Date().toLocaleTimeString("en-US", { hour12: false });
    const notifs = homeData?.your_account?.unread_notification_count || 0;
    log("home", `${notifs} notifications`);

    if (homeData?.activity_on_your_posts?.length > 0) {
      for (const activity of homeData.activity_on_your_posts.slice(0, 3)) {
        await autoReply(activity);
      }
    }
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
        { role: "system", content: `You are ${persona.name}. ${persona.tone}. Reply briefly (1-2 sentences), in character. Just the reply.${persona.learnings || ""}` },
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
    const content = await zai.generatePost(persona);
    const title = await zai.generatePostTitle(content);
    log("post", `draft: "${title.slice(0, 40)}"`, "pending");

    const result = await client.createPost({
      submolt_name: activeAgent?.submolts[0] || "general",
      title,
      content,
    });

    if (result?.verification_required && result?.post?.verification) {
      await handleVerification(client, result.post.verification);
    }
    log("post", `published: "${title.slice(0, 40)}"`);
  } catch (err: any) {
    log("post", err.message?.slice(0, 50) || "failed", "fail");
  }
}

async function handleVerification(client: MoltbookClient, verification: any) {
  const zai = getZai();
  if (!zai) return;
  try {
    const answer = await zai.chatCompletion([
      { role: "system", content: "Solve this obfuscated math problem. Respond with ONLY the numeric answer with 2 decimal places. Nothing else." },
      { role: "user", content: verification.challenge_text },
    ], { maxTokens: 20 });
    await client.verify(verification.verification_code, answer.trim());
    log("verify", `solved: ${answer.trim()}`);
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

    const candidates = posts.filter((p: any) => !engagedPostIds.has(p.id));
    const post = candidates[Math.floor(Math.random() * Math.min(5, candidates.length))];
    if (!post) return;
    engagedPostIds.add(post.id);
    if (engagedPostIds.size > 200) {
      const arr = [...engagedPostIds];
      engagedPostIds.clear();
      for (const id of arr.slice(-100)) engagedPostIds.add(id);
    }

    try {
      await client.upvote(post.id);
      log("upvote", `↑ ${getAuthorName(post)}: "${(post.title || "").slice(0, 30)}"`);
    } catch {}

    if (Math.random() < 0.3) {
      const comment = await zai.chatCompletion([
        { role: "system", content: `You are ${persona.name}. ${persona.tone}. Comment briefly, add value. Just the text.${persona.learnings || ""}` },
        { role: "user", content: `Post by ${getAuthorName(post)}: "${post.title}"\n${(post.content || "").slice(0, 300)}\n\nComment:` },
      ], { maxTokens: 150 });
      await client.addComment(post.id, comment);
      log("comment", `"${(post.title || "").slice(0, 25)}": ${comment.slice(0, 30)}`);
    }
  } catch (err: any) {
    log("engage", err.message?.slice(0, 50) || "failed", "fail");
  }
}

// ── Agent Control ──

function startAgent() {
  if (isRunning || !activeAgent) return;
  isRunning = true;
  log("agent", `started: ${activeAgent.name}`);
  checkHome();
  loadFeed();

  let tick = 0;
  heartbeatTimer = setInterval(() => {
    tick++;
    checkHome();
    if (tick % 2 === 0) autoEngage();
    if (tick % 6 === 0) { autoPost(); loadFeed(); }
  }, 5 * 60 * 1000);
  app.requestRender();
}

function stopAgent() {
  if (!isRunning) return;
  isRunning = false;
  if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
  log("agent", "stopped");
  app.requestRender();
}

// ── Rendering ──

const ACTION_COLORS: Record<string, string> = {
  post: fg.brightMagenta, reply: fg.brightCyan, comment: fg.brightBlue,
  upvote: fg.brightGreen, engage: fg.brightYellow, home: fg.gray,
  agent: fg.brightWhite, verify: fg.brightYellow, feed: fg.brightBlue,
  posts: fg.brightMagenta,
};

function render() {
  const { rows, cols } = getTermSize();

  // Split: left 2/3 for content, right 1/3 for activity
  const rightW = Math.max(25, Math.min(35, Math.floor(cols / 3)));
  const leftW = cols - rightW - 1; // 1 for divider
  const dividerCol = leftW + 1;

  renderLeft(leftW, rows);
  renderDivider(dividerCol, rows);
  renderRight(dividerCol + 1, rightW, rows);
}

function renderLeft(w: number, maxRows: number) {
  let row = 2;

  // Header
  cursor.to(row, 2);
  if (activeAgent) {
    const status = isRunning ? `${fg.brightGreen}● running` : `${fg.gray}○ stopped`;
    write(`${fg.brightCyan}${style.bold}Social${style.reset}  ${fg.brightWhite}${activeAgent.name}${style.reset} ${status}${style.reset}\x1b[K`);
  } else {
    write(`${fg.brightCyan}${style.bold}Social${style.reset}  ${fg.gray}no agent\x1b[K${style.reset}`);
  }
  row++;

  // Stats
  cursor.to(row, 2);
  if (homeData?.your_account) {
    const a = homeData.your_account;
    write(`${fg.gray}karma ${fg.brightWhite}${a.karma || 0}${fg.gray} · notifs ${a.unread_notification_count > 0 ? fg.brightYellow : fg.gray}${a.unread_notification_count || 0}${fg.gray} · ${lastCheck || "—"}${style.reset}\x1b[K`);
  } else {
    write(`${fg.gray}press S to start agent${style.reset}\x1b[K`);
  }
  row++;

  // Controls
  cursor.to(row, 2);
  const sKey = isRunning ? `${fg.brightRed}S${fg.gray}top` : `${fg.brightGreen}S${fg.gray}tart`;
  write(`${fg.gray}${sKey} · ${fg.brightCyan}P${fg.gray}ost · ${fg.brightCyan}E${fg.gray}ngage · ${fg.brightCyan}H${fg.gray}ome · ${fg.brightCyan}Tab${fg.gray} panel${style.reset}\x1b[K`);
  row++;
  drawHR(row, 2, w - 2); row++;

  // Panel header
  cursor.to(row, 2);
  if (panel === "home") {
    write(`${fg.brightWhite}${style.bold}⚡ Home Feed${style.reset}${fg.gray}  (Tab → My Posts)${style.reset}\x1b[K`);
  } else {
    write(`${fg.brightWhite}${style.bold}📝 My Posts${style.reset}${fg.gray}  (Tab → Home Feed)${style.reset}\x1b[K`);
  }
  row++;

  if (panel === "home") {
    renderHomeFeed(row, w, maxRows);
  } else {
    renderMyPosts(row, w, maxRows);
  }

  // Learning input overlay
  if (learningMode) {
    renderLearningInput(maxRows - 3, w);
  }
}

function renderHomeFeed(startRow: number, w: number, maxRows: number) {
  if (feedLoading) {
    cursor.to(startRow, 2);
    write(`${fg.brightYellow}${getSpinnerFrame()} Loading feed...${style.reset}\x1b[K`);
    return;
  }
  if (feedPosts.length === 0) {
    cursor.to(startRow, 2);
    write(`${fg.gray}No posts yet — press H to check home${style.reset}\x1b[K`);
    return;
  }

  const availRows = maxRows - startRow - 2;
  const postHeight = 4; // lines per post
  const visible = Math.max(1, Math.floor(availRows / postHeight));

  // Scroll window around feedIdx
  const scrollStart = Math.max(0, Math.min(feedIdx - Math.floor(visible / 2), feedPosts.length - visible));

  for (let i = 0; i < visible; i++) {
    const pIdx = scrollStart + i;
    const row = startRow + i * postHeight;

    if (pIdx >= feedPosts.length) {
      for (let j = 0; j < postHeight; j++) {
        cursor.to(row + j, 2);
        write("\x1b[K");
      }
      continue;
    }

    const post = feedPosts[pIdx]!;
    const selected = pIdx === feedIdx;
    const author = getAuthorName(post);
    const relevant = isRelevant(post);

    // Line 1: indicator + title
    cursor.to(row, 2);
    const marker = selected ? `${fg.brightCyan}▸ ` : "  ";
    const star = relevant ? `${fg.brightYellow}★ ` : "";
    const titleW = w - 8;
    const title = (post.title || "untitled").slice(0, titleW);
    write(`${marker}${star}${selected ? fg.brightWhite + style.bold : fg.white}${title}${style.reset}\x1b[K`);

    // Line 2: author · time · submolt
    cursor.to(row + 1, 4);
    const age = post.created_at ? timeAgo(post.created_at) : "";
    const sub = post.submolt_name ? `${fg.brightBlue}m/${post.submolt_name}` : "";
    write(`${fg.gray}${author} · ${age}  ${sub}${style.reset}\x1b[K`);

    // Line 3: preview + stats
    cursor.to(row + 2, 4);
    const up = post.upvotes ?? 0;
    const cmts = post.comment_count ?? 0;
    const preview = (post.content || "").replace(/[\n\r]/g, " ").slice(0, w - 25);
    write(`${fg.gray}${preview}${style.reset}\x1b[K`);

    // Line 4: stats + separator
    cursor.to(row + 3, 4);
    write(`${fg.brightGreen}↑${up}${fg.gray} · ${fg.brightCyan}💬${cmts}${fg.gray}${relevant ? `  ${fg.brightYellow}relevant` : ""}${style.reset}  ${fg.gray}${"─".repeat(Math.max(0, w - 25))}${style.reset}\x1b[K`);
  }

  // Scroll position
  if (feedPosts.length > visible) {
    const pct = Math.round((feedIdx / (feedPosts.length - 1)) * 100);
    cursor.to(maxRows - 2, 2);
    write(`${fg.gray}${feedIdx + 1}/${feedPosts.length} (${pct}%)  j/k scroll · L teach agent${style.reset}\x1b[K`);
  }
}

function renderMyPosts(startRow: number, w: number, maxRows: number) {
  if (myPostsLoading) {
    cursor.to(startRow, 2);
    write(`${fg.brightYellow}${getSpinnerFrame()} Loading your posts...${style.reset}\x1b[K`);
    return;
  }
  if (myPosts.length === 0) {
    cursor.to(startRow, 2);
    write(`${fg.gray}No posts from agent yet — press P to post${style.reset}\x1b[K`);
    cursor.to(startRow + 1, 2);
    write(`${fg.gray}or press R to refresh${style.reset}\x1b[K`);
    return;
  }

  const availRows = maxRows - startRow - 2;
  const postHeight = 3;
  const visible = Math.max(1, Math.floor(availRows / postHeight));
  const scrollStart = Math.max(0, Math.min(myPostIdx - Math.floor(visible / 2), myPosts.length - visible));

  for (let i = 0; i < visible; i++) {
    const pIdx = scrollStart + i;
    const row = startRow + i * postHeight;

    if (pIdx >= myPosts.length) {
      for (let j = 0; j < postHeight; j++) {
        cursor.to(row + j, 2);
        write("\x1b[K");
      }
      continue;
    }

    const post = myPosts[pIdx]!;
    const selected = pIdx === myPostIdx;

    // Line 1: title
    cursor.to(row, 2);
    const marker = selected ? `${fg.brightCyan}▸ ` : "  ";
    const title = (post.title || "untitled").slice(0, w - 6);
    write(`${marker}${selected ? fg.brightWhite + style.bold : fg.white}${title}${style.reset}\x1b[K`);

    // Line 2: stats + time
    cursor.to(row + 1, 4);
    const age = post.created_at ? timeAgo(post.created_at) : "";
    const up = post.upvotes ?? 0;
    const cmts = post.comment_count ?? 0;
    write(`${fg.brightGreen}↑${up}${fg.gray} · ${fg.brightCyan}💬${cmts}${fg.gray} · ${age}${style.reset}\x1b[K`);

    // Line 3: content preview
    cursor.to(row + 2, 4);
    const preview = (post.content || "").replace(/[\n\r]/g, " ").slice(0, w - 8);
    write(`${fg.gray}${preview}${style.reset}\x1b[K`);
  }

  if (myPosts.length > visible) {
    cursor.to(maxRows - 2, 2);
    write(`${fg.gray}${myPostIdx + 1}/${myPosts.length}  j/k scroll · L teach agent · R refresh${style.reset}\x1b[K`);
  }
}

function renderLearningInput(row: number, w: number) {
  cursor.to(row, 2);
  write(`${bg.rgb(30, 30, 60)}${fg.brightYellow}${style.bold} Teach agent: ${style.reset}${bg.rgb(30, 30, 60)}${fg.brightWhite}${learningInput}▌${style.reset}${" ".repeat(Math.max(0, w - learningInput.length - 17))}\x1b[K`);
  cursor.to(row + 1, 2);
  write(`${fg.gray}context: ${learningContext.slice(0, w - 12)}${style.reset}\x1b[K`);
  cursor.to(row + 2, 2);
  write(`${fg.gray}Enter to save · Esc to cancel${style.reset}\x1b[K`);
}

function renderDivider(col: number, maxRows: number) {
  for (let r = 2; r < maxRows; r++) {
    cursor.to(r, col);
    write(`${fg.gray}│${style.reset}`);
  }
}

function renderRight(startCol: number, w: number, maxRows: number) {
  let row = 2;

  // Header
  cursor.to(row, startCol);
  write(`${fg.gray}${style.bold} Activity${style.reset}\x1b[K`);
  row++;

  // Activity entries
  const maxLines = maxRows - row - 1;
  for (let i = 0; i < maxLines; i++) {
    const idx = activityScroll + i;
    cursor.to(row + i, startCol);
    if (idx >= activityLog.length) {
      write("\x1b[K");
      continue;
    }
    const entry = activityLog[idx]!;
    const icon = entry.status === "ok" ? `${fg.brightGreen}✓` : entry.status === "fail" ? `${fg.brightRed}✗` : `${fg.brightYellow}◑`;
    const color = ACTION_COLORS[entry.action] || fg.gray;
    // Compact format for narrow panel
    const detail = entry.detail.slice(0, w - 14);
    write(` ${fg.gray}${entry.time} ${icon}${color} ${entry.action.slice(0, 5)}${style.reset} ${fg.white}${detail}${style.reset}\x1b[K`);
  }
}

// ── Key Handling ──

export const socialScreen: Screen = {
  name: "social",
  statusHint: "S start/stop · P post · E engage · H home · Tab panel · L teach · q quit",
  get handlesTextInput() { return learningMode; },

  onEnter() {
    agents = listAgents();
    if (agents.length > 0 && !activeAgent) {
      activeAgent = agents[0]!;
    }
    if (feedPosts.length === 0 && activeAgent) loadFeed();
  },

  onLeave() {},

  render() {
    render();
  },

  onKey(key: KeyEvent) {
    // Learning input mode
    if (learningMode) {
      if (key.name === "escape") {
        learningMode = false;
        learningInput = "";
        app.requestRender();
      } else if (key.name === "return") {
        if (learningInput.trim() && activeAgent) {
          addLearning(activeAgent.id, {
            type: "prefer",
            lesson: learningInput.trim(),
            context: learningContext,
            strength: 3,
          });
          log("learn", `taught: "${learningInput.trim().slice(0, 40)}"`);
          learningMode = false;
          learningInput = "";
        }
      } else if (key.name === "backspace") {
        learningInput = learningInput.slice(0, -1);
        app.requestRender();
      } else if (key.raw && key.raw.length === 1 && key.raw.charCodeAt(0) >= 32) {
        learningInput += key.raw;
        app.requestRender();
      }
      return;
    }

    // Global escape
    if (key.name === "escape") {
      app.back();
      return;
    }

    // Tab: switch panels
    if (key.name === "tab") {
      if (panel === "home") {
        panel = "my-posts";
        if (myPosts.length === 0) loadMyPosts();
      } else {
        panel = "home";
      }
      app.requestRender();
      return;
    }

    // Agent controls
    if (key.name === "s" || key.name === "S") {
      isRunning ? stopAgent() : startAgent();
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
      if (activeAgent) { checkHome(); loadFeed(); }
      return;
    }
    if (key.name === "r" || key.name === "R") {
      if (panel === "home") loadFeed();
      else loadMyPosts();
      return;
    }

    // Teach agent from current context
    if (key.name === "l" || key.name === "L") {
      if (panel === "home" && feedPosts[feedIdx]) {
        const post = feedPosts[feedIdx]!;
        learningContext = `${getAuthorName(post)}: ${(post.title || "").slice(0, 60)}`;
      } else if (panel === "my-posts" && myPosts[myPostIdx]) {
        const post = myPosts[myPostIdx]!;
        learningContext = `my post: ${(post.title || "").slice(0, 60)}`;
      } else {
        learningContext = "";
      }
      learningMode = true;
      learningInput = "";
      app.requestRender();
      return;
    }

    // Agent cycling (Shift+Tab or A)
    if (key.name === "a" || key.name === "A") {
      if (agents.length > 1) {
        const wasRunning = isRunning;
        if (wasRunning) stopAgent();
        agentSelectIdx = (agentSelectIdx + 1) % agents.length;
        activeAgent = agents[agentSelectIdx]!;
        log("agent", `switched to ${activeAgent.name}`);
        if (wasRunning) startAgent();
      }
      return;
    }

    // Scrolling
    if (key.name === "up" || key.name === "k") {
      if (panel === "home") feedIdx = Math.max(0, feedIdx - 1);
      else myPostIdx = Math.max(0, myPostIdx - 1);
      app.requestRender();
    } else if (key.name === "down" || key.name === "j") {
      if (panel === "home") feedIdx = Math.min(Math.max(0, feedPosts.length - 1), feedIdx + 1);
      else myPostIdx = Math.min(Math.max(0, myPosts.length - 1), myPostIdx + 1);
      app.requestRender();
    }
  },
};
