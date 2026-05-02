# molt.tui

personal AI agent that posts and engages on social platforms on my behalf.

## what it is

an autonomous agentic AI system that handles social media presence (primarily X / Twitter) without manual posting. implements an agent harness with decision-making over content patterns, scheduling, and reply behavior. built in TypeScript with LLM orchestration.

## why it exists

I post regularly to grow technical reach but the daily overhead of writing, scheduling, and replying eats focus from real work. molt.tui handles the routine pieces — drafting variants, tracking what landed, surfacing replies that need a real human response — while keeping me in the loop on anything substantive.

it is named molt.tui because the original interface was a TUI; current iteration is closer to a long-running daemon.

## features

- agent loop with LLM tool calling
- content generation against pattern templates I've defined
- decision-making over post timing and reply triage
- knows when to hand off to me vs respond autonomously

## stack

- TypeScript (Bun runtime)
- LLM provider integration (OpenAI / Anthropic / Gemini)
- agent harness written from scratch (no LangChain)

## install

```bash
bun install
```

## run

```bash
bun run index.ts
```

## status

WIP. core agent loop works; reply triage is the active development area. not yet packaged for general use — this is tuned to my own posting patterns and account, but the harness is reusable.

## license

see LICENSE file.
