# Design

BotDesk's visual identity and UI design, decided here before it is built in `apps/web`.

## Order of work

1. **Logo** → [logo/](logo/README.md) (done: the botdesk wordmark with an online light on the o; files, icons, favicons, social images)
2. **Brand tokens**: colour, type, radius, motion, derived from the chosen logo
3. **Avatar system** for bots (BotDesk's own, never Grok's blob with eyes)
4. **App shell and screens**, built on the tokens

Each step is approved by the owner before the next one starts.

## Rules

- Original work only. Match Grok Bot's flows and layout ([teardown](../research/grok-bot-teardown.md)), never its assets, mascot or logo.
- Every concept is reviewed as a rendered image, not as code. Sources (`.html`) live next to their renders (`.png`) so a round can be re-rendered.
- Once a direction is chosen, delete the rejected rounds and write down what they taught in the README.
