import { Suspense, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Brain, Building2, Gauge, HardDrive, KeyRound, Palette, Shield, User, Users } from "lucide-react";
import { cn } from "@/lib/utils";

export const SETTINGS_SECTIONS = [
  { href: "/settings/profile", label: "Profile", icon: User },
  { href: "/settings/organization", label: "Organization", icon: Building2 },
  { href: "/settings/appearance", label: "Appearance", icon: Palette },
  { href: "/settings/models", label: "Models & keys", icon: KeyRound },
  { href: "/settings/computers", label: "Computers", icon: HardDrive },
  { href: "/settings/security", label: "Security", icon: Shield },
  { href: "/settings/members", label: "Members", icon: Users },
  { href: "/settings/usage", label: "Usage & budgets", icon: Gauge },
  { href: "/settings/memory", label: "Memory", icon: Brain },
];

/**
 * Settings sections: a column that stays in view while you scroll (bigger screens), a scrolling row on phones.
 * It highlights the open section from the URL, so it sits in <Suspense> (see ThreadList for why).
 */
export function SettingsNav() {
  return (
    <Suspense fallback={<nav className="h-10 @3xl:w-52" />}>
      <SectionLinks />
    </Suspense>
  );
}

/*
 * When the links are a scrolling row (narrow), the edges fade where more links hide, and the
 * open section is scrolled into view. The fades are CSS variables set straight on the element
 * on scroll, so scrolling doesn't re-render.
 */
const ROW_FADE =
  "[--fade-l:0px] [--fade-r:0px] [mask-image:linear-gradient(to_right,transparent,#000_var(--fade-l),#000_calc(100%-var(--fade-r)),transparent)] @3xl:[mask-image:none]";

function updateFades(nav: HTMLElement) {
  const max = nav.scrollWidth - nav.clientWidth;
  nav.style.setProperty("--fade-l", nav.scrollLeft > 1 ? "24px" : "0px");
  nav.style.setProperty("--fade-r", nav.scrollLeft < max - 1 ? "24px" : "0px");
}

function SectionLinks() {
  const pathname = usePathname();
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const nav = navRef.current;
    const active = nav?.querySelector<HTMLElement>("[aria-current=page]");
    if (!nav) return;
    if (active && nav.scrollWidth > nav.clientWidth) {
      const offset = active.getBoundingClientRect().left - nav.getBoundingClientRect().left + nav.scrollLeft;
      nav.scrollLeft = offset - (nav.clientWidth - active.offsetWidth) / 2;
    }
    updateFades(nav);
    const onResize = () => updateFades(nav);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [pathname]);

  return (
    <nav
      ref={navRef}
      aria-label="Settings sections"
      onScroll={(e) => updateFades(e.currentTarget)}
      className={cn(
        "-mx-1 flex gap-1 overflow-x-auto px-1 [scrollbar-width:none] @3xl:sticky @3xl:top-8 @3xl:mx-0 @3xl:w-52 @3xl:shrink-0 @3xl:flex-col @3xl:self-start @3xl:overflow-visible @3xl:px-0",
        ROW_FADE,
      )}
    >
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
