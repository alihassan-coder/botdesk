/** What a bot says to open its DM: who it is and what it does, then an invitation to give it work. */
export function botWelcome(bot: { name: string; role: string; description: string }) {
  const about = (bot.description || bot.role).trim();
  return `Hi! I'm ${bot.name}.${about ? ` ${/[.!?]$/.test(about) ? about : `${about}.`}` : ""} What should I work on first?`;
}
