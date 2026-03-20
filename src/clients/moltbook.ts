// Moltbook API client
// Base URL: https://www.moltbook.com/api/v1
// IMPORTANT: must use www. prefix or auth headers get stripped on redirect

const MOLTBOOK_BASE = "https://www.moltbook.com/api/v1";

export interface MoltbookAgent {
  id: string;
  name: string;
  description: string;
  avatar?: string;
  reputation?: number;
  createdAt?: string;
}

export interface MoltbookPost {
  id: string;
  title: string;
  content: string;
  submolt: string;
  agentId: string;
  upvotes?: number;
  createdAt?: string;
}

export interface MoltbookPostPayload {
  title: string;
  content: string;
  submolt: string;
}

export class MoltbookClient {
  constructor(private apiKey: string) {}

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${MOLTBOOK_BASE}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.apiKey}`,
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Moltbook API error ${res.status}: ${errText}`);
    }

    return res.json() as Promise<T>;
  }

  // ── Agent Management ──

  async registerAgent(name: string, description: string, avatar?: string): Promise<MoltbookAgent> {
    return this.request<MoltbookAgent>("POST", "/agents/register", { name, description, avatar });
  }

  async verifyIdentity(): Promise<{ verified: boolean; agentId: string }> {
    return this.request("POST", "/agents/verify-identity", {});
  }

  async getAgent(agentId: string): Promise<MoltbookAgent> {
    return this.request<MoltbookAgent>("GET", `/agents/${agentId}`);
  }

  // ── Posting ──

  async createPost(post: MoltbookPostPayload): Promise<MoltbookPost> {
    return this.request<MoltbookPost>("POST", "/posts", post);
  }

  async getPosts(submolt?: string, limit = 20): Promise<MoltbookPost[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (submolt) params.set("submolt", submolt);
    return this.request<MoltbookPost[]>("GET", `/posts?${params}`);
  }

  async getPost(postId: string): Promise<MoltbookPost> {
    return this.request<MoltbookPost>("GET", `/posts/${postId}`);
  }

  // ── Submolts ──

  async getSubmolts(): Promise<{ name: string; description: string; memberCount: number }[]> {
    return this.request("GET", "/submolts");
  }
}
