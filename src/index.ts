#!/usr/bin/env bun
// Molt.tui - Agent management TUI for Moltbook
// Zero-dependency, runs on desktop + Android (Termux)

import { app } from "./tui/app.ts";
import { dashboardScreen } from "./screens/dashboard.ts";
import { agentsScreen } from "./screens/agents.ts";
import { createAgentScreen } from "./screens/create-agent.ts";
import { editAgentScreen } from "./screens/edit-agent.ts";
import { generateScreen } from "./screens/generate.ts";
import { postScreen } from "./screens/post.ts";
import { feedScreen } from "./screens/feed.ts";
import { settingsScreen } from "./screens/settings.ts";
import { tasksScreen } from "./screens/tasks.ts";
import { onboardingScreen, needsOnboarding } from "./screens/onboarding.ts";
import { ensureDirs } from "./utils/config.ts";

// Ensure config directories exist
ensureDirs();

// Register all screens
app.register(dashboardScreen);
app.register(agentsScreen);
app.register(createAgentScreen);
app.register(editAgentScreen);
app.register(generateScreen);
app.register(postScreen);
app.register(feedScreen);
app.register(settingsScreen);
app.register(tasksScreen);
app.register(onboardingScreen);

// Launch — show onboarding on first run, dashboard otherwise
app.start(needsOnboarding() ? "onboarding" : "dashboard");
