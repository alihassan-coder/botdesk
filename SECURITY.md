# Security policy

BotDesk's bots act inside people's email and other apps, so we take security seriously. Thank you for helping keep users safe.

## Reporting a vulnerability

**Please don't open a public GitHub issue for security problems.** Report them privately instead:

- **Email:** alihassan.coder@gmail.com, with the subject line starting `[SECURITY]`
- **Or** use GitHub's private vulnerability reporting: the repository's **Security** tab → **Report a vulnerability**

Please include:

1. What the problem is and what an attacker could do with it
2. Steps to reproduce it (a proof of concept helps a lot)
3. The version or commit you tested, and your setup (self-hosted or not, operating system)
4. How you'd like to be credited, if at all

## What happens next

| When | What we do |
|---|---|
| Within 3 days | Confirm we received your report |
| Within 10 days | Tell you whether we can reproduce it, and how serious we think it is |
| When fixed | Release the fix, then publish an advisory that credits you (unless you'd rather stay anonymous) |

Please give us a reasonable time to fix the problem before you share details publicly. We'll keep you updated along the way.

## Supported versions

BotDesk is in early development and has no releases yet. Security fixes go to the `main` branch. Once releases begin, this table will list which versions get fixes.

| Version | Supported |
|---|---|
| `main` | ✅ |

## What counts

Examples of what we especially want to hear about:

- Seeing or changing another organization's data
- Bypassing sign-in, session or role checks
- A bot running a risky action without the approval it should need
- Prompt injection that makes a bot leak data or act against its user
- Leaking secrets: API keys, OAuth tokens, passwords

Out of scope: problems that need an already-compromised device, social engineering, denial-of-service by flooding, and reports from automated scanners without a demonstrated impact.

## Safe harbour

We won't take legal action against good-faith research that respects this policy. That means no data destruction, no accessing other people's data beyond what's needed to show the problem, and no service disruption.
