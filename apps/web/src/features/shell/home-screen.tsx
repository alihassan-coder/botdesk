"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { useLatestThreadId, usePendingApprovalCount } from "@/data/store";
import { BotdeskLockup } from "./logo";
import { ThreadList } from "./thread-list";

const PHONE = "(max-width: 767px)";

/**
 * "/" — On phones this is the home screen: the list of your bots and groups.
 * On tablets and desktops the sidebar already shows that list, so we open your latest chat.
 */
export function HomeScreen() {
  const router = useRouter();
  const latestThreadId = useLatestThreadId();
  const pendingApprovals = usePendingApprovalCount();

  useEffect(() => {
    // Read the screen size directly: it's correct on the very first effect, unlike the first render.
    if (latestThreadId && !window.matchMedia(PHONE).matches) router.replace(`/chat/${latestThreadId}`);
  }, [latestThreadId, router]);

  return (
    <>
      <div className="flex h-full flex-col md:hidden">
        <header className="flex h-14 shrink-0 items-center gap-2.5 border-b px-4">
          <BotdeskLockup />
          <Button asChild variant="ghost" size="icon-sm" className="relative ml-auto" aria-label={`Approvals, ${pendingApprovals} waiting`}>
            <Link href="/approvals">
              <Inbox />
              {pendingApprovals > 0 && (
                <span className="absolute -top-0.5 -right-0.5 grid size-4 place-items-center rounded-full bg-brand text-[10px] font-semibold text-brand-foreground">
                  {pendingApprovals}
                </span>
              )}
            </Link>
          </Button>
          {/* Opens the full sidebar: routines, apps, marketplace, settings, theme. */}
          <SidebarTrigger aria-label="Menu" />
        </header>
        <div className="flex-1 overflow-y-auto px-2 py-3">
          <ThreadList />
        </div>
      </div>
      <div className="hidden h-full items-center justify-center text-sm text-muted-foreground md:flex">
        Opening your latest chat…
      </div>
    </>
  );
}
