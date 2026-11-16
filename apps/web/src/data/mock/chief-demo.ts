/**
 * MOCK DATA: the Chief demo (ADR 0014). Ask Chief to "plan the launch" and it hands two Tasks
 * to teammates, waits while each one works and replies, then posts one combined answer.
 * Only src/data/store.ts imports it, and plays it on timers.
 */

/** What starts the demo: a message to Chief that asks it to plan the launch. */
export const trigger = /\bplan\b.*\blaunch\b/i;

export const chiefId = "b_chief";

/** Chief's words above the cards. It doesn't @mention the bots it hands to (that would start a second reply). */
export const opener =
  "I'll split this up. Sales Outbound drafts the announcement emails, and Inbox Manager pulls what customers asked for this week so the launch answers it. I'll put the plan together when both are back.";

export const tasks = [
  {
    toBotId: "b_sales",
    task: "Draft three launch announcement emails: one for current customers, one for trial users, one for cold leads.",
    reply:
      "Three launch emails are drafted and parked in Gmail as drafts.\n\n- **Customers:** leads with the two most requested features, and a thank-you for the feedback.\n- **Trial users:** a 20% first-month offer, valid until Friday.\n- **Cold leads:** short, one link to the changelog, no attachment.\n\nNothing is sent. Tell me who should review them first.",
  },
  {
    toBotId: "b_inbox",
    task: "List the top customer requests from this week's inbox, with how many people asked for each.",
    reply:
      "This week's top requests, from 46 customer emails:\n\n1. **SSO for small teams**: 14 asked.\n2. **CSV export of reports**: 9 asked.\n3. **A Slack digest**: 6 asked.\n\nAcme and Globex both asked about SSO and are waiting on a date.",
  },
] as const;

/** Chief's combined answer, once both Tasks are done. */
export const finalAnswer =
  "Here's the launch plan, with what the team found.\n\n**Tuesday:** ship SSO for small teams first. It's the top request (14 customers, Acme and Globex among them), so it leads every announcement.\n\n**Wednesday:** send the three launch emails Sales Outbound drafted (customers, trial users, cold leads). They're drafts in Gmail; nothing goes out until you approve.\n\n**Next sprint:** CSV export (9 asked), then the Slack digest (6).\n\nWant me to book a review of the emails for Tuesday morning?";
