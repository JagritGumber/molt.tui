// Bird CLI wrapper — posts to X/Twitter via @steipete/bird
// Uses cookie-based auth (AUTH_TOKEN + CT0 env vars)
// WARNING: posting via unofficial API carries account suspension risk

import { execFileSync } from "child_process";

function bird(args: string[]): string {
  try {
    return execFileSync("bird", args, {
      encoding: "utf-8",
      timeout: 30_000,
      env: { ...process.env },
    }).trim();
  } catch (err: any) {
    throw new Error(`bird: ${err.stderr?.slice(0, 200) || err.message?.slice(0, 200) || "failed"}`);
  }
}

export function birdCheck(): { ok: boolean; user?: string } {
  try {
    const out = bird(["whoami", "--plain"]);
    const match = out.match(/@(\w+)/);
    return { ok: true, user: match?.[1] || "unknown" };
  } catch {
    return { ok: false };
  }
}

export function birdTweet(text: string): string {
  const trimmed = text.slice(0, 280);
  return bird(["tweet", trimmed, "--plain"]);
}

export function birdUserTweets(handle: string, count = 10): string {
  return bird(["user-tweets", `@${handle}`, "-n", String(count), "--plain"]);
}

export function birdHome(count = 10): string {
  return bird(["home", "--following", "-n", String(count), "--plain"]);
}
