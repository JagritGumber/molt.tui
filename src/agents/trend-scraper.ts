// Trend Scraper — watches HN, X trending, and tech news for tweet-worthy content
// Runs in background, surfaces trending topics for tweet generation

export interface TrendItem {
  source: "hn" | "x" | "tech";
  title: string;
  url?: string;
  score: number;      // engagement/points
  fetchedAt: number;
}

// Fetch HN front page (top stories with high engagement)
export async function fetchHNTrends(limit = 10): Promise<TrendItem[]> {
  try {
    const res = await fetch("https://hacker-news.firebaseio.com/v0/topstories.json");
    const ids = (await res.json()) as number[];
    const top = ids.slice(0, limit);

    const items = await Promise.all(top.map(async (id) => {
      const r = await fetch(`https://hacker-news.firebaseio.com/v0/item/${id}.json`);
      const item = (await r.json()) as { title?: string; url?: string; score?: number };
      return {
        source: "hn" as const,
        title: item?.title || "",
        url: item?.url || `https://news.ycombinator.com/item?id=${id}`,
        score: item?.score || 0,
        fetchedAt: Date.now(),
      };
    }));

    return items.filter(i => i.title && i.score > 50);
  } catch {
    return [];
  }
}

// Fetch X/Twitter trending topics via bird CLI (if available)
export async function fetchXTrends(): Promise<TrendItem[]> {
  try {
    const { execFileSync } = await import("child_process");
    const out = execFileSync("bird", ["news", "-n", "10", "--plain"], {
      encoding: "utf-8",
      timeout: 15_000,
      env: { ...process.env },
    }).trim();

    // Parse bird news output — each trend is a line
    return out.split("\n")
      .filter(line => line.trim().length > 10)
      .slice(0, 10)
      .map(line => ({
        source: "x" as const,
        title: line.replace(/^\d+\.\s*/, "").trim().slice(0, 100),
        score: 0,
        fetchedAt: Date.now(),
      }));
  } catch {
    return [];
  }
}

// Combine all trend sources, dedupe, sort by relevance
export async function fetchAllTrends(): Promise<TrendItem[]> {
  const [hn, x] = await Promise.all([fetchHNTrends(), fetchXTrends()]);
  const all = [...hn, ...x];

  // Dedupe by similar titles
  const seen = new Set<string>();
  return all.filter(item => {
    const key = item.title.toLowerCase().slice(0, 30);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
