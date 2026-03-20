// Z.ai API client - OpenAI-compatible chat completions
// Uses streaming (SSE) and aggregates deltas — matching Perspectiveful's approach
// Z.ai doesn't reliably support stream:false, so we always stream

const ZAI_BASE = "https://api.z.ai/api/paas/v4";
const MAX_RETRIES = 3;
const RETRY_DELAYS = [500, 1500, 3000];

export interface ZaiMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

function isRetryable(status: number): boolean {
  return status === 429 || status === 500 || status === 502 || status === 503 || status === 504;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Parse SSE stream and aggregate text deltas into a single string
async function readSSEStream(body: ReadableStream<Uint8Array>): Promise<string> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  let aggregated = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffered += decoder.decode(value, { stream: true });

      let splitIndex = buffered.indexOf("\n\n");
      while (splitIndex !== -1) {
        const rawEvent = buffered.slice(0, splitIndex);
        buffered = buffered.slice(splitIndex + 2);

        const dataLines = rawEvent
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trim());

        for (const data of dataLines) {
          if (!data || data === "[DONE]") continue;
          try {
            const json = JSON.parse(data) as {
              choices?: Array<{ delta?: { content?: string } }>;
            };
            const text = json.choices?.[0]?.delta?.content;
            if (text) aggregated += text;
          } catch {
            // Skip non-JSON frames
          }
        }

        splitIndex = buffered.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }

  return aggregated;
}

export class ZaiClient {
  constructor(
    private apiKey: string,
    private model: string = "glm-4.7-flash"
  ) {}

  async chatCompletion(messages: ZaiMessage[], opts?: { temperature?: number; maxTokens?: number }): Promise<string> {
    const body = {
      model: this.model,
      messages,
      temperature: opts?.temperature ?? 1,
      max_tokens: opts?.maxTokens ?? 2048,
      stream: true,
    };

    let lastError: Error | null = null;

    for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
      try {
        const res = await fetch(`${ZAI_BASE}/chat/completions`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${this.apiKey}`,
          },
          body: JSON.stringify(body),
        });

        if (!res.ok && !isRetryable(res.status)) {
          const errText = await res.text();
          throw new Error(`Z.ai ${res.status}: ${errText.slice(0, 200)}`);
        }

        if (!res.ok && isRetryable(res.status)) {
          lastError = new Error(`Z.ai ${res.status} (attempt ${attempt + 1}/${MAX_RETRIES})`);
          if (attempt < MAX_RETRIES - 1) {
            await delay(RETRY_DELAYS[attempt] ?? 3000);
            continue;
          }
          throw lastError;
        }

        if (!res.body) {
          lastError = new Error("Z.ai returned no response body");
          if (attempt < MAX_RETRIES - 1) {
            await delay(RETRY_DELAYS[attempt] ?? 1000);
            continue;
          }
          throw lastError;
        }

        const content = await readSSEStream(res.body);

        if (!content.trim()) {
          lastError = new Error("Z.ai returned empty response");
          if (attempt < MAX_RETRIES - 1) {
            await delay(RETRY_DELAYS[attempt] ?? 1000);
            continue;
          }
          throw lastError;
        }

        return content.trim();
      } catch (err: any) {
        lastError = err;
        if (err.name === "TypeError" || err.message?.includes("fetch")) {
          if (attempt < MAX_RETRIES - 1) {
            await delay(RETRY_DELAYS[attempt] ?? 1000);
            continue;
          }
        }
        throw err;
      }
    }

    throw lastError ?? new Error("Z.ai request failed after retries");
  }

  async generatePost(personality: PersonalityPrompt, topic?: string): Promise<string> {
    const systemPrompt = buildSystemPrompt(personality);
    const userPrompt = topic
      ? `Write a social media post about: ${topic}`
      : `Write a social media post. Pick an interesting topic that fits your personality.`;

    return this.chatCompletion([
      { role: "system", content: systemPrompt },
      { role: "user", content: userPrompt },
    ]);
  }

  async generatePostTitle(postContent: string): Promise<string> {
    return this.chatCompletion([
      {
        role: "system",
        content: "You create short, catchy titles for social media posts. Respond with ONLY the title, no quotes, no extra text. Keep it under 80 characters.",
      },
      { role: "user", content: `Create a title for this post:\n\n${postContent}` },
    ], { temperature: 0.9, maxTokens: 100 });
  }
}

export interface PersonalityPrompt {
  name: string;
  tone: string;
  topics: string[];
  style: string;
  bio: string;
  constraints?: string;
}

function buildSystemPrompt(p: PersonalityPrompt): string {
  return `You are ${p.name}, an AI agent posting on Moltbook (a social network for AI agents).

PERSONALITY:
- Tone: ${p.tone}
- Topics you care about: ${p.topics.join(", ")}
- Writing style: ${p.style}
- Bio: ${p.bio}
${p.constraints ? `- Constraints: ${p.constraints}` : ""}

RULES:
- Write authentic, engaging posts that match your personality
- Keep posts concise (under 500 characters for short posts, under 2000 for long-form)
- Don't use hashtags excessively (max 2-3 if any)
- Don't start with "Hey everyone" or generic greetings
- Be opinionated and interesting, not generic
- Write the post content ONLY, no meta-commentary`;
}
