import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { Inbox, Moon, Plug, Plus, Repeat, Settings, Store, Sun } from "lucide-react";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { useBots, useThreads } from "@/data/store";
import { BotAvatar } from "@/features/bots/bot-avatar";

const PAGES = [
  { label: "Approvals", href: "/approvals", icon: Inbox },
  { label: "Routines", href: "/routines", icon: Repeat },
  { label: "Connect apps", href: "/apps", icon: Plug },
  { label: "Marketplace", href: "/marketplace", icon: Store },
  { label: "Settings", href: "/settings", icon: Settings },
];

/** ⌘K / Ctrl+K anywhere: jump to a bot, a group or a page, create a bot, or switch the theme. */
export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const threads = useThreads();
  const bots = useBots();
  const { resolvedTheme, setTheme } = useTheme();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((isOpen) => !isOpen);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  /** Close the palette, then do the thing. */
  const run = (action: () => void) => () => {
    setOpen(false);
    action();
  };

  return (
    <CommandDialog open={open} onOpenChange={setOpen} title="Command palette" description="Jump to a bot, a group or a page">
      <Command>
        <CommandInput placeholder="Search bots, groups and pages…" />
        <CommandList>
          <CommandEmpty>Nothing matches.</CommandEmpty>
          <CommandGroup heading="Bots and groups">
            {threads.map((thread) => {
              const bot = bots.find((b) => b.id === thread.botId);
              return (
                <CommandItem key={thread.id} value={`${thread.title} ${bot?.role ?? "group"}`} onSelect={run(() => router.push(`/chat/${thread.id}`))}>
                  {bot ? <BotAvatar name={bot.name} color={bot.avatarColor} size="sm" /> : <span className="grid size-6 place-items-center rounded-md bg-muted text-xs">#</span>}
                  {thread.title}
                  <span className="text-xs text-muted-foreground">{bot?.role ?? "Group"}</span>
                </CommandItem>
              );
            })}
          </CommandGroup>
          <CommandSeparator />
          <CommandGroup heading="Go to">
            {PAGES.map(({ label, href, icon: Icon }) => (
              <CommandItem key={href} onSelect={run(() => router.push(href))}>
                <Icon /> {label}
              </CommandItem>
            ))}
          </CommandGroup>
          <CommandSeparator />
          <CommandGroup heading="Actions">
            <CommandItem onSelect={run(() => router.push("/bots/new"))}>
              <Plus /> New bot
            </CommandItem>
            <CommandItem onSelect={run(() => setTheme(resolvedTheme === "dark" ? "light" : "dark"))}>
              {resolvedTheme === "dark" ? <Sun /> : <Moon />} Switch to {resolvedTheme === "dark" ? "light" : "dark"} mode
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
