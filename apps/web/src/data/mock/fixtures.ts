/**
 * MOCK DATA: delete this folder once apps/api is live.
 * Only src/data/store.ts imports it.
 */
import type {
  Approval,
  Bot,
  Connection,
  Connector,
  MemoryItem,
  Message,
  Model,
  Org,
  ProviderCredential,
  Routine,
  Template,
  Thread,
  UsageDay,
  User,
} from "../types";

/*
 * Mock timestamps are measured back from a fixed moment, not from the real clock.
 * Reading the clock here would give the server and the browser different data,
 * and Next.js refuses to prerender pages that read the current time.
 * Keep this moment in the past: as days go by the mock simply looks older.
 */
const MOCK_NOW = Date.parse("2026-11-12T05:00:00Z");
const ago = (minutes: number) => new Date(MOCK_NOW - minutes * 60_000).toISOString();

export const org: Org = { id: "org_1", name: "Acme Labs", slug: "acme", plan: "team" };

export const users: User[] = [
  { id: "u_me", name: "Ali Hassan", email: "ali@acme.dev", handle: "ali", role: "owner", presence: "online" },
  { id: "u_sara", name: "Sara Khan", email: "sara@acme.dev", handle: "sara", role: "admin", presence: "online" },
  { id: "u_omar", name: "Omar Farooq", email: "omar@acme.dev", handle: "omar", role: "member", presence: "away" },
];

export const currentUserId = "u_me";

/**
 * MOCK ONLY: sign-in passwords for the demo accounts above. The real API stores
 * password hashes (Better Auth); passwords never live in the web app.
 */
export const mockPasswords: Record<string, string> = {
  "ali@acme.dev": "botdesk123",
  "sara@acme.dev": "botdesk123",
  "omar@acme.dev": "botdesk123",
};

export const models: Model[] = [
  { id: "m_grok", provider: "xAI", name: "Grok 4.5", capabilities: ["vision", "tools", "reasoning"], priceInPerMTok: 3, priceOutPerMTok: 15, contextWindow: 256_000 },
  { id: "m_claude", provider: "Anthropic", name: "Claude Sonnet 5.5", capabilities: ["vision", "tools", "reasoning", "computer-use"], priceInPerMTok: 3, priceOutPerMTok: 15, contextWindow: 1_000_000 },
  { id: "m_gpt", provider: "OpenAI", name: "GPT-5.5", capabilities: ["vision", "tools", "reasoning", "computer-use"], priceInPerMTok: 2.5, priceOutPerMTok: 10, contextWindow: 400_000 },
  { id: "m_gemini", provider: "Google", name: "Gemini 3 Pro", capabilities: ["vision", "tools", "reasoning"], priceInPerMTok: 2, priceOutPerMTok: 12, contextWindow: 1_000_000 },
  { id: "m_deepseek", provider: "DeepSeek", name: "DeepSeek V4", capabilities: ["tools", "reasoning"], priceInPerMTok: 0.3, priceOutPerMTok: 1.2, contextWindow: 128_000 },
  { id: "m_llama", provider: "Ollama (local)", name: "Llama 4 Scout", capabilities: ["tools"], priceInPerMTok: 0, priceOutPerMTok: 0, contextWindow: 128_000 },
];

export const bots: Bot[] = [
  {
    id: "b_chief", name: "Chief", handle: "chief", role: "Chief of staff", isChief: true,
    description: "Runs the team. Splits work, assigns it to the right bot, and only pulls you in for judgment calls.",
    avatarColor: "indigo", status: "working", statusText: "Coordinating 3 handoffs",
    modelId: "m_claude", securityLevel: "ask-before-acting", computerMode: "own", connectionIds: ["c_gmail"],
    instructions: "You coordinate the other bots. Keep Ali's day clear. Batch questions.", createdAt: ago(60 * 24 * 20),
    monthlyBudgetUsd: 80, spentThisMonthUsd: 31.4,
  },
  {
    id: "b_inbox", name: "Inbox Manager", handle: "inbox", role: "Email triage",
    description: "Keeps your inbox at zero. Drafts replies in your voice and parks anything that needs you.",
    avatarColor: "violet", status: "waiting-approval", statusText: "2 replies waiting for you",
    modelId: "m_gpt", securityLevel: "ask-before-acting", computerMode: "none", connectionIds: ["c_gmail"],
    instructions: "Triage the inbox every morning. Never send without approval.", createdAt: ago(60 * 24 * 18),
    monthlyBudgetUsd: 40, spentThisMonthUsd: 18.9,
  },
  {
    id: "b_sales", name: "Sales Outbound", handle: "sales", role: "Outbound sales",
    description: "Finds leads, writes personal openers, and queues follow-ups.",
    avatarColor: "sky", status: "idle", statusText: "Next run tonight at 11 PM",
    modelId: "m_grok", securityLevel: "ask-before-acting", computerMode: "own", connectionIds: ["c_gmail"],
    instructions: "Target seed-stage dev-tool founders.", createdAt: ago(60 * 24 * 12),
    monthlyBudgetUsd: 60, spentThisMonthUsd: 44.2,
  },
  {
    id: "b_talent", name: "Talent Scout", handle: "talent", role: "Recruiting",
    description: "Sources candidates, drafts intros, and books screens.",
    avatarColor: "emerald", status: "sleeping", statusText: "Sleeping until Monday 9 AM",
    modelId: "m_gemini", securityLevel: "read-only", computerMode: "own", connectionIds: [],
    instructions: "Hiring: senior TypeScript engineers, remote.", createdAt: ago(60 * 24 * 9),
    monthlyBudgetUsd: 30, spentThisMonthUsd: 6.1,
  },
  {
    id: "b_expense", name: "Expense Manager", handle: "expenses", role: "Finance ops",
    description: "Pulls receipts from email, files expenses, and flags anything odd.",
    avatarColor: "amber", status: "idle", statusText: "Filed 9 receipts today",
    modelId: "m_deepseek", securityLevel: "ask-before-acting", computerMode: "none", connectionIds: ["c_gmail"],
    instructions: "Anything above $500 needs approval.", createdAt: ago(60 * 24 * 6),
    monthlyBudgetUsd: 15, spentThisMonthUsd: 2.3,
  },
  {
    id: "b_bugs", name: "Bug Fixer", handle: "bugs", role: "Engineering",
    description: "Reproduces bugs on its computer, files tickets, and hands off fixes.",
    avatarColor: "rose", status: "error", statusText: "Lost access to staging",
    modelId: "m_claude", securityLevel: "autonomous", computerMode: "own", connectionIds: [],
    instructions: "Repro first, then file. Never push to main.", createdAt: ago(60 * 24 * 3),
    monthlyBudgetUsd: 50, spentThisMonthUsd: 12.7,
  },
];

export const threads: Thread[] = [
  { id: "t_chief", kind: "dm", title: "Chief", botId: "b_chief", participants: [{ type: "user", id: "u_me" }, { type: "bot", id: "b_chief" }], lastMessageAt: ago(4), lastMessagePreview: "Done. Overnight outbound is now a weekly routine.", unread: 1, pinned: true },
  { id: "t_inbox", kind: "dm", title: "Inbox Manager", botId: "b_inbox", participants: [{ type: "user", id: "u_me" }, { type: "bot", id: "b_inbox" }], lastMessageAt: ago(22), lastMessagePreview: "Inbox at zero. 2 replies need your OK.", unread: 2 },
  { id: "t_launch", kind: "group", title: "Launch crew", participants: [{ type: "user", id: "u_me" }, { type: "user", id: "u_sara" }, { type: "bot", id: "b_chief" }, { type: "bot", id: "b_sales" }, { type: "bot", id: "b_bugs" }], lastMessageAt: ago(48), lastMessagePreview: "Sara: @bugs can you check the signup flow?", unread: 0 },
  { id: "t_sales", kind: "dm", title: "Sales Outbound", botId: "b_sales", participants: [{ type: "user", id: "u_me" }, { type: "bot", id: "b_sales" }], lastMessageAt: ago(120), lastMessagePreview: "36 drafts queued, 0 sent.", unread: 0 },
  { id: "t_talent", kind: "dm", title: "Talent Scout", botId: "b_talent", participants: [{ type: "user", id: "u_me" }, { type: "bot", id: "b_talent" }], lastMessageAt: ago(300), lastMessagePreview: "3 intros drafted in your voice.", unread: 0 },
  { id: "t_expense", kind: "dm", title: "Expense Manager", botId: "b_expense", participants: [{ type: "user", id: "u_me" }, { type: "bot", id: "b_expense" }], lastMessageAt: ago(400), lastMessagePreview: "Report filed. 9 receipts, nothing odd.", unread: 0 },
  { id: "t_bugs", kind: "dm", title: "Bug Fixer", botId: "b_bugs", participants: [{ type: "user", id: "u_me" }, { type: "bot", id: "b_bugs" }], lastMessageAt: ago(600), lastMessagePreview: "Staging login expired. Can you take over?", unread: 0 },
];

export const approvals: Approval[] = [
  {
    id: "a_1", botId: "b_inbox", threadId: "t_inbox", riskClass: "external-send", status: "pending",
    title: "Send reply to Vicky (Globex)", summary: "Confirms the Thursday call and attaches the pricing sheet.",
    preview: [
      { label: "To", value: "vicky@globex.com" },
      { label: "Subject", value: "Re: Thursday call" },
      { label: "Body", value: "Hi Vicky,\n\nThursday at 3 PM works. I've attached our pricing sheet so we can go through it together.\n\nBest,\nAli" },
    ],
    connectionId: "c_gmail", requestedAt: ago(20),
  },
  {
    id: "a_2", botId: "b_inbox", threadId: "t_inbox", riskClass: "external-send", status: "pending",
    title: "Decline vendor demo (Initech)", summary: "Politely declines and asks them to check back in Q2.",
    preview: [
      { label: "To", value: "sales@initech.com" },
      { label: "Subject", value: "Re: Quick demo?" },
      { label: "Body", value: "Thanks for reaching out. We're not evaluating tools this quarter. Happy to reconnect in Q2." },
    ],
    connectionId: "c_gmail", requestedAt: ago(18),
  },
  {
    id: "a_3", botId: "b_bugs", threadId: "t_bugs", riskClass: "credential", status: "pending",
    title: "Take over to log in to staging", summary: "The staging session expired. Log in on the bot's computer so it can keep going.",
    preview: [{ label: "Site", value: "staging.acme.dev/login" }],
    requestedAt: ago(600),
  },
  {
    id: "a_4", botId: "b_expense", threadId: "t_expense", riskClass: "spend", status: "approved",
    title: "Reimburse $742 to Omar", summary: "Conference travel, receipts attached.",
    preview: [{ label: "Amount", value: "$742.00" }, { label: "To", value: "Omar Farooq" }],
    requestedAt: ago(60 * 26), decidedBy: "u_me", decidedAt: ago(60 * 25),
  },
];

export const messages: Message[] = [
  // Chief DM
  { id: "m1", threadId: "t_chief", author: { type: "user", id: "u_me" }, createdAt: ago(95), parts: [{ type: "text", text: "Line up tonight's outbound. Pull the hottest accounts from this week's threads and queue openers for the top ones." }] },
  { id: "m2", threadId: "t_chief", author: { type: "bot", id: "b_chief" }, createdAt: ago(94), parts: [
    { type: "reasoning", text: "Two sources: Account threads flagged by Inbox Manager, and the CRM pipeline. Sales Outbound owns drafting. I'll hand off and check the queue before anything sends.", durationSec: 6 },
    { type: "text", text: "On it. Handing the drafting to @sales and pulling flagged accounts from @inbox." },
    { type: "handoff", fromBotId: "b_chief", toBotId: "b_sales", task: "Draft openers for tonight's top accounts" },
  ] },
  { id: "m3", threadId: "t_chief", author: { type: "bot", id: "b_chief" }, createdAt: ago(40), parts: [
    { type: "work-log", title: "Tonight's outbound", items: [
      { label: "Inbox", detail: "Acme + Globex threads flagged as priority", done: true },
      { label: "LinkedIn", detail: "4 profiles skipped (recently contacted)", done: true },
      { label: "Sequencer", detail: "36 drafts queued, 0 sent", done: true },
    ] },
    { type: "computer-task", title: "Queue drafts in the sequencer", app: "LinkedIn", status: "done", stepCount: 42 },
    { type: "text", text: "The 36 drafts are sitting in the queue on my screen: recipient, opener, and a Draft badge on each. Nothing goes out until you've had a look." },
  ] },
  { id: "m4", threadId: "t_chief", author: { type: "user", id: "u_me" }, createdAt: ago(6), parts: [{ type: "text", text: "The top 10 look good. Send them. Run this every week." }], reactions: [{ emoji: "👍", count: 1 }] },
  { id: "m5", threadId: "t_chief", author: { type: "bot", id: "b_chief" }, createdAt: ago(4), parts: [
    { type: "routine-created", routineId: "r_1", name: "Overnight outbound" },
    { type: "text", text: "Done. Overnight outbound is now a weekly routine. I'll ask before the first live send." },
  ] },

  // Inbox DM
  { id: "m10", threadId: "t_inbox", author: { type: "bot", id: "b_inbox" }, createdAt: ago(25), parts: [
    { type: "work-log", title: "Morning triage", items: [
      { label: "Archived", detail: "41 newsletters and notifications", done: true },
      { label: "Labeled", detail: "12 threads → Customers, Hiring, Finance", done: true },
      { label: "Drafted", detail: "5 replies in your voice", done: true },
      { label: "Parked", detail: "2 replies need your OK", done: false },
    ] },
    { type: "text", text: "Inbox at zero. Two replies need your OK before I send them." },
  ] },
  { id: "m11", threadId: "t_inbox", author: { type: "bot", id: "b_inbox" }, createdAt: ago(20), parts: [{ type: "approval", approvalId: "a_1" }] },
  { id: "m12", threadId: "t_inbox", author: { type: "bot", id: "b_inbox" }, createdAt: ago(18), parts: [{ type: "approval", approvalId: "a_2" }] },
  { id: "m13", threadId: "t_inbox", author: { type: "bot", id: "b_inbox" }, createdAt: ago(17), parts: [{ type: "question", question: "Should I auto-archive vendor cold emails from now on?", options: ["Yes, always", "Ask me each time", "No"] }] },

  // Launch crew group
  { id: "m20", threadId: "t_launch", author: { type: "user", id: "u_sara" }, createdAt: ago(55), mentions: [{ type: "bot", id: "b_bugs" }], parts: [{ type: "text", text: "@bugs can you check the signup flow? Two users said the verify email never arrived." }] },
  { id: "m21", threadId: "t_launch", author: { type: "bot", id: "b_bugs" }, createdAt: ago(52), parts: [
    { type: "computer-task", title: "Reproduce signup on staging", app: "Chromium", status: "needs-takeover", stepCount: 7 },
    { type: "text", text: "I got to the login screen but the staging session expired. @ali can you take over for a sec so I can log in?" },
    { type: "approval", approvalId: "a_3" },
  ], mentions: [{ type: "user", id: "u_me" }] },
  { id: "m22", threadId: "t_launch", author: { type: "bot", id: "b_chief" }, createdAt: ago(50), parts: [{ type: "text", text: "While that's blocked, @sales: hold the launch-announcement sequence until signup is confirmed working." }], mentions: [{ type: "bot", id: "b_sales" }] },
  { id: "m23", threadId: "t_launch", author: { type: "bot", id: "b_sales" }, createdAt: ago(48), parts: [{ type: "text", text: "Paused. 120 launch emails held in drafts." }] },

  // Sales
  { id: "m30", threadId: "t_sales", author: { type: "bot", id: "b_sales" }, createdAt: ago(120), parts: [
    { type: "computer-task", title: "Research 40 founders", app: "Chromium", status: "done", stepCount: 128 },
    { type: "text", text: "36 drafts queued, 0 sent. Skipped 4 people we contacted in the last 30 days." },
  ] },
  // Talent
  { id: "m40", threadId: "t_talent", author: { type: "bot", id: "b_talent" }, createdAt: ago(300), parts: [
    { type: "text", text: "3 intros drafted in your voice, held for review. I'm read-only, so I can't send them; promote me to “Ask before acting” if you want me to." },
    { type: "file", name: "candidates-week-45.csv", mime: "text/csv", sizeBytes: 18_204 },
  ] },
  // Expense
  { id: "m50", threadId: "t_expense", author: { type: "bot", id: "b_expense" }, createdAt: ago(400), parts: [
    { type: "work-log", title: "Expense report", items: [
      { label: "Receipts found", detail: "9 in Gmail", done: true },
      { label: "Filed", detail: "$1,284.10 total", done: true },
      { label: "Flags", detail: "Nothing odd", done: true },
    ] },
    { type: "approval", approvalId: "a_4" },
  ] },
  // Bugs
  { id: "m60", threadId: "t_bugs", author: { type: "bot", id: "b_bugs" }, createdAt: ago(600), parts: [
    { type: "text", text: "Staging login expired. Can you take over?" },
    { type: "approval", approvalId: "a_3" },
  ] },
];

export const connectors: Connector[] = [
  {
    id: "gmail", name: "Gmail", publisher: "BotDesk", category: "email", authType: "oauth2", available: true,
    description: "Read, search, label, draft and send email. Triggers on new mail.",
    tools: [
      { name: "search", description: "Search messages", risk: "read" },
      { name: "read", description: "Read a thread", risk: "read" },
      { name: "label", description: "Add or remove labels", risk: "write-internal" },
      { name: "archive", description: "Archive threads", risk: "write-internal" },
      { name: "draft", description: "Create a draft", risk: "write-internal" },
      { name: "send", description: "Send an email", risk: "external-send" },
      { name: "delete", description: "Move to trash", risk: "destructive" },
    ],
    triggers: ["new_email", "label_added"],
  },
  { id: "gcal", name: "Google Calendar", publisher: "BotDesk", category: "calendar", authType: "oauth2", available: false, description: "Find times, book and move meetings.", tools: [], triggers: [] },
  { id: "slack", name: "Slack", publisher: "BotDesk", category: "chat", authType: "oauth2", available: false, description: "Read channels, post messages, and reply in threads.", tools: [], triggers: [] },
  { id: "github", name: "GitHub", publisher: "BotDesk", category: "dev", authType: "oauth2", available: false, description: "Issues, pull requests and code search.", tools: [], triggers: [] },
  { id: "linear", name: "Linear", publisher: "BotDesk", category: "dev", authType: "oauth2", available: false, description: "Create and update issues.", tools: [], triggers: [] },
  { id: "notion", name: "Notion", publisher: "BotDesk", category: "docs", authType: "oauth2", available: false, description: "Search and edit pages and databases.", tools: [], triggers: [] },
  { id: "hubspot", name: "HubSpot", publisher: "Community", category: "crm", authType: "oauth2", available: false, description: "Contacts, deals and sequences.", tools: [], triggers: [] },
  { id: "stripe", name: "Stripe", publisher: "Community", category: "finance", authType: "api-key", available: false, description: "Payments, invoices and refunds.", tools: [], triggers: [] },
  { id: "mcp", name: "Custom MCP server", publisher: "You", category: "mcp", authType: "none", available: true, description: "Connect any remote MCP server by URL. Its tools become bot tools.", tools: [], triggers: [] },
];

export const connections: Connection[] = [
  { id: "c_gmail", connectorId: "gmail", account: "ali@acme.dev", owner: "user", status: "connected", connectedAt: ago(60 * 24 * 20) },
];

export const routines: Routine[] = [
  { id: "r_1", botId: "b_chief", name: "Overnight outbound", description: "Pull hot accounts, queue openers, send the top 10 after approval.", schedule: "Every Monday at 11 PM", source: "chat", steps: ["Collect priority threads from Inbox Manager", "Ask Sales Outbound for openers", "Skip anyone contacted in the last 30 days", "Ask for approval, then send the top 10"], enabled: true },
  { id: "r_2", botId: "b_inbox", name: "Morning triage", description: "Archive noise, label, draft replies, park what needs you.", schedule: "Weekdays at 7 AM", source: "recording", steps: ["Open Gmail", "Archive newsletters", "Label customer threads", "Draft replies", "Post a summary"], lastRunAt: ago(25), lastOutcome: "needs-approval", enabled: true },
  { id: "r_3", botId: "b_expense", name: "Weekly expenses", description: "Find receipts and file the report.", schedule: "Fridays at 5 PM", source: "recording", steps: ["Search Gmail for receipts", "Extract amounts", "File the report", "Flag anything over $500"], lastRunAt: ago(400), lastOutcome: "success", enabled: true },
];

export const credentials: ProviderCredential[] = [
  { id: "k_1", provider: "Anthropic", label: "Org key", owner: "org", maskedKey: "sk-ant-…4f2a", lastUsedAt: ago(4) },
  { id: "k_2", provider: "OpenAI", label: "Ali's key", owner: "user", maskedKey: "sk-…9c1d", lastUsedAt: ago(20) },
  { id: "k_3", provider: "xAI", label: "Org key", owner: "org", maskedKey: "xai-…77b0", lastUsedAt: ago(120) },
  { id: "k_4", provider: "Custom (OpenAI-compatible)", label: "Local vLLM", owner: "org", baseUrl: "http://gpu-box:8000/v1", maskedKey: "none" },
];

export const memories: MemoryItem[] = [
  { id: "mem_1", text: "Ali prefers short emails that end with “Best, Ali”.", source: "Inbox Manager, from edits to 6 drafts", createdAt: ago(60 * 24 * 4) },
  { id: "mem_2", botId: "b_sales", text: "Don't contact anyone reached in the last 30 days.", source: "Chat with Chief", createdAt: ago(60 * 24 * 2) },
  { id: "mem_3", text: "Thursdays after 2 PM are for customer calls.", source: "Calendar pattern", createdAt: ago(60 * 24 * 7) },
  { id: "mem_4", botId: "b_expense", text: "Anything over $500 needs approval.", source: "Bot instructions", createdAt: ago(60 * 24 * 6) },
];

export const usage: UsageDay[] = Array.from({ length: 14 }, (_, i) => {
  const d = new Date(MOCK_NOW);
  d.setUTCDate(d.getUTCDate() - (13 - i));
  return {
    date: d.toISOString().slice(0, 10),
    tokensUsd: Math.round((3 + Math.sin(i / 2) * 2 + i * 0.3) * 100) / 100,
    computerUsd: Math.round((1 + Math.cos(i / 3) + i * 0.1) * 100) / 100,
  };
});

export const templates: Template[] = [
  { id: "tpl_inbox", name: "Inbox Zero", role: "Email triage", description: "Triage, label, draft in your voice, park what needs you.", avatarColor: "violet", installs: 12_400, connectors: ["gmail"], category: "Productivity" },
  { id: "tpl_sdr", name: "Outbound SDR", role: "Sales", description: "Research leads, write openers, run sequences.", avatarColor: "sky", installs: 8_120, connectors: ["gmail"], category: "Sales" },
  { id: "tpl_recruit", name: "Recruiter", role: "Recruiting", description: "Source, screen and book interviews.", avatarColor: "emerald", installs: 5_310, connectors: ["gmail"], category: "People" },
  { id: "tpl_exp", name: "Expense Clerk", role: "Finance", description: "Receipts in, reports out.", avatarColor: "amber", installs: 4_870, connectors: ["gmail"], category: "Finance" },
  { id: "tpl_qa", name: "QA Tester", role: "Engineering", description: "Clicks through your app every night and files what breaks.", avatarColor: "rose", installs: 3_990, connectors: [], category: "Engineering" },
  { id: "tpl_research", name: "Researcher", role: "Research", description: "Deep multi-source research with cited reports.", avatarColor: "orange", installs: 9_760, connectors: [], category: "Research" },
];
