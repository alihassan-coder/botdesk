import { Suspense } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Brain, Gauge, KeyRound, Palette, Shield, User, Users } from "lucide-react";
import { cn } from "@/lib/utils";

export const SETTINGS_SECTIONS = [
  { href: "/settings/profile", label: "Profile", icon: User },
  { href: "/settings/appearance", label: "Appearance", icon: Palette },
  { href: "/settings/models", label: "Models & keys", icon: KeyRound },
  { href: "/settings/security", label: "Security", icon: Shield },
  { href: "/settings/members", label: "Members", icon: Users },
  { href: "/settings/usage", label: "Usage & budgets", icon: Gauge },
  { href: "/settings/memory", label: "Memory", icon: Brain },
];

/**
 * Settings sections: a column on bigger screens, a scrolling row on phones.
 * It highlights the open section from the URL, so it sits in <Suspense> (see ThreadList for why).
 */
export function SettingsNav() {
  return (
    <Suspense fallback={<nav className="h-10 md:w-52" />}>
      <SectionLinks />
    </Suspense>
  );
}

function SectionLinks() {
  const pathname = usePathname();
  return (
    <nav aria-label="Settings sections" className="-mx-1 flex gap-1 overflow-x-auto px-1 [scrollbar-width:none] md:mx-0 md:w-52 md:shrink-0 md:flex-col md:overflow-visible md:px-0">
      {SETTINGS_SECTIONS.map(({ href, label, icon: Icon }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex shrink-0 items-center gap-2 rounded-[10px] px-3 py-2 text-sm transition-colors",
              active ? "bg-muted font-medium" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
            )}
          >
            <Icon className="size-4" /> {label}
          </Link>
        );
      })}
    </nav>
  );
}
