// Z.ai API client - OpenAI-compatible chat completions
// Endpoint: https://api.z.ai/api/paas/v4/chat/completions
// Retry + empty response handling inspired by NullClaw's model multiplexer

const ZAI_BASE = "https://api.z.ai/api/paas/v4";
const MAX_RETRIES = 3;
const RETRY_DELAYS = [500, 1500, 3000]; // progressive backoff (ms)

export interface ZaiMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ZaiCompletionRequest {
  model: string;
  messages: ZaiMessage[];
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
  stream?: boolean;
}

export interface ZaiCompletionResponse {
  id: string;
  choices: {
    index: number;
    message: { role: string; content: string };
    finish_reason: string;
  }[];
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

// Errors that are worth retrying (transient)
function isRetryable(status: number): boolean {
  return status === 429 || status === 500 || status === 502 || status === 503 || status === 504;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Extract content from response, handling various empty/malformed shapes
function extractContent(data: any): string | null {
  // Standard path
  const content = data?.choices?.[0]?.message?.content;
  if (content && typeof content === "string" && content.trim().length > 0) {
    return content.trim();
  }

  // Some models put content in delta instead of message
  const delta = data?.choices?.[0]?.delta?.content;
  if (delta && typeof delta === "string" && delta.trim().length > 0) {
    return delta.trim();
  }

  // Check if choices exist but are empty array
  if (Array.isArray(data?.choices) && data.choices.length === 0) {
    return null;
  }

  // Check for content being null/undefined/empty string explicitly
  if (content === "" || content === null || content === undefined) {
    return null;
  }

  return null;
}

export class ZaiClient {
  constructor(
    private apiKey: string,
    private model: string = "GLM-4.7-FlashX"
  ) {}

  async chatCompletion(messages: ZaiMessage[], opts?: { temperature?: number; maxTokens?: number }): Promise<string> {
    const body: ZaiCompletionRequest = {
      model: this.model,
      messages,
      temperature: opts?.temperature ?? 1,
      max_tokens: opts?.maxTokens ?? 2048,
      stream: false,
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

        // Non-retryable HTTP error — fail immediately
        if (!res.ok && !isRetryable(res.status)) {
          const errText = await res.text();
          throw new Error(`Z.ai ${res.status}: ${errText.slice(0, 200)}`);
        }

        // Retryable HTTP error — wait and retry
        if (!res.ok && isRetryable(res.status)) {
          lastError = new Error(`Z.ai ${res.status} (attempt ${attempt + 1}/${MAX_RETRIES})`);
          if (attempt < MAX_RETRIES - 1) {
            await delay(RETRY_DELAYS[attempt] ?? 3000);
            continue;
          }
          throw lastError;
        }

        const data = await res.json();
        const content = extractContent(data);

        // Empty response — retry with slightly higher temperature
        if (!content) {
          lastError = new Error("Z.ai returned empty response");
          if (attempt < MAX_RETRIES - 1) {
            body.temperature = Math.min(1.0, (body.temperature ?? 0.8) + 0.1);
            await delay(RETRY_DELAYS[attempt] ?? 1000);
            continue;
          }
          throw lastError;
        }

        return content;
      } catch (err: any) {
        lastError = err;
        // Network errors (fetch failed) — retry
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
