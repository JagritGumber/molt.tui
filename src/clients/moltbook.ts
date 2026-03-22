// Moltbook API client
// Base URL: https://www.moltbook.com/api/v1
// IMPORTANT: must use www. prefix or auth headers get stripped on redirect
// Full API docs: https://www.moltbook.com/skill.md

const MOLTBOOK_BASE = "https://www.moltbook.com/api/v1";

export interface MoltbookAgent {
  name: string;
  description?: string;
  karma?: number;
  api_key?: string;
  claim_url?: string;
  verification_code?: string;
}

export interface MoltbookPost {
  id: string;
  title: string;
  content: string;
  submolt_name: string;
  upvotes?: number;
  comment_count?: number;
  created_at?: string;
  author_name?: string;
}

export interface MoltbookRegisterResponse {
  agent: MoltbookAgent;
  important: string;
}

export interface MoltbookVerification {
  verification_code: string;
  challenge_text: string;
  expires_at: string;
  instructions: string;
}

// ── Registration (no auth required) ──

export async function registerOnMoltbook(name: string, description?: string): Promise<MoltbookRegisterResponse> {
  const res = await fetch(`${MOLTBOOK_BASE}/agents/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Register failed ${res.status}: ${errText.slice(0, 200)}`);
  }
  return res.json() as Promise<MoltbookRegisterResponse>;
}

// ── Authenticated client ──

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
      throw new Error(`Moltbook ${res.status}: ${errText.slice(0, 200)}`);
    }

    return res.json() as Promise<T>;
  }

  // ── Agent ──

  async getMe(): Promise<{ success: boolean; agent: MoltbookAgent }> {
    return this.request("GET", "/agents/me");
  }

  async getStatus(): Promise<{ status: string }> {
    return this.request("GET", "/agents/status");
  }

  async getHome(): Promise<any> {
    return this.request("GET", "/home");
  }

  // ── Posts ──

  async createPost(post: { submolt_name: string; title: string; content?: string }): Promise<any> {
    return this.request("POST", "/posts", post);
  }

  async getFeed(sort = "hot", limit = 25): Promise<any> {
    return this.request("GET", `/posts?sort=${sort}&limit=${limit}`);
  }

  async getPost(postId: string): Promise<any> {
    return this.request("GET", `/posts/${postId}`);
  }

  // ── Comments ──

  async addComment(postId: string, content: string, parentId?: string): Promise<any> {
    const body: any = { content };
    if (parentId) body.parent_id = parentId;
    return this.request("POST", `/posts/${postId}/comments`, body);
  }

  async getComments(postId: string, sort = "best"): Promise<any> {
    return this.request("GET", `/posts/${postId}/comments?sort=${sort}`);
  }

  // ── Voting ──

  async upvote(postId: string): Promise<any> {
    return this.request("POST", `/posts/${postId}/upvote`);
  }

  async downvote(postId: string): Promise<any> {
    return this.request("POST", `/posts/${postId}/downvote`);
  }

  async upvoteComment(commentId: string): Promise<any> {
    return this.request("POST", `/comments/${commentId}/upvote`);
  }

  // ── Profile ──

  async getProfile(name: string): Promise<any> {
    return this.request("GET", `/agents/profile?name=${encodeURIComponent(name)}`);
  }

  async updateMe(data: { description?: string }): Promise<any> {
    return this.request("PATCH", "/agents/me", data);
  }

  // ── Feed ──

  async getSubmoltFeed(submoltName: string, sort = "hot"): Promise<any> {
    return this.request("GET", `/submolts/${submoltName}/feed?sort=${sort}`);
  }

  // ── Submolts ──

  async getSubmolts(): Promise<any> {
    return this.request("GET", "/submolts");
  }

  async subscribe(submoltName: string): Promise<any> {
    return this.request("POST", `/submolts/${submoltName}/subscribe`);
  }

  // ── Verification ──

  async verify(verificationCode: string, answer: string): Promise<any> {
    return this.request("POST", "/verify", { verification_code: verificationCode, answer });
  }

  // ── Search ──

  async search(query: string, type = "all", limit = 20): Promise<any> {
    const q = encodeURIComponent(query);
    return this.request("GET", `/search?q=${q}&type=${type}&limit=${limit}`);
  }

  // ── Following ──

  async follow(agentName: string): Promise<any> {
    return this.request("POST", `/agents/${agentName}/follow`);
  }

  async unfollow(agentName: string): Promise<any> {
    return this.request("DELETE", `/agents/${agentName}/follow`);
  }

  // ── Notifications ──

  async markPostRead(postId: string): Promise<any> {
    return this.request("POST", `/notifications/read-by-post/${postId}`);
  }

  async markAllRead(): Promise<any> {
    return this.request("POST", "/notifications/read-all");
  }
}
