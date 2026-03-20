// Z.ai API client - OpenAI-compatible chat completions
// Endpoint: https://api.z.ai/api/paas/v4/chat/completions

const ZAI_BASE = "https://api.z.ai/api/paas/v4";

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

export class ZaiClient {
  constructor(
    private apiKey: string,
    private model: string = "glm-4.7-flashx"
  ) {}

  async chatCompletion(messages: ZaiMessage[], opts?: { temperature?: number; maxTokens?: number }): Promise<string> {
    const body: ZaiCompletionRequest = {
      model: this.model,
      messages,
      temperature: opts?.temperature ?? 0.8,
      max_tokens: opts?.maxTokens ?? 2048,
    };

    const res = await fetch(`${ZAI_BASE}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Z.ai API error ${res.status}: ${errText}`);
    }

    const data = (await res.json()) as ZaiCompletionResponse;
    const content = data.choices[0]?.message?.content;
    if (!content) throw new Error("Z.ai returned empty response");
    return content;
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
