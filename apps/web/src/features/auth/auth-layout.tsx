import { Check } from "lucide-react";
import { BotdeskLockup, BotdeskMark } from "@/features/shell/logo";

/**
 * The frame for sign in, sign up and password reset: a dark brand panel with what
 * BotDesk does (bigger screens), and the form on the right.
 */
export function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-svh lg:grid-cols-[1fr_minmax(0,560px)]">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-neutral-950 p-12 text-white lg:flex">
        <BotdeskLockup className="text-white" />

        {/* A <p>, not a heading: each auth page's own title is its one h1. */}
        <div className="flex max-w-md flex-col gap-8">
          <p className="text-5xl font-semibold tracking-[-0.045em] leading-[1.02]">
            Your AI team.
            <br />
            Always on.
          </p>
          <p className="text-lg text-neutral-400">Bots that work in your apps, talk in threads, and ask before anything risky.</p>

          {/* A taste of the product: the moment a bot asks before acting. */}
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4 backdrop-blur" aria-hidden>
            <div className="flex items-center gap-2 text-sm">
              <span className="grid size-6 place-items-center rounded-md bg-violet-600 text-[11px] font-semibold">I</span>
              <span className="font-medium">Inbox Manager</span>
              <span className="ml-auto text-xs text-neutral-500">now</span>
            </div>
            <p className="mt-3 text-sm text-neutral-300">Send reply to Vicky (Globex): confirms Thursday and attaches pricing.</p>
            <div className="mt-3 flex gap-2">
              <span className="flex items-center gap-1 rounded-lg bg-white px-2.5 py-1 text-xs font-medium text-black">
                <Check className="size-3" /> Approve
              </span>
              <span className="rounded-lg border border-white/15 px-2.5 py-1 text-xs">Edit</span>
            </div>
          </div>
        </div>

        <p className="text-sm text-neutral-500">Open source (MIT). Host it yourself or use ours.</p>
        <BotdeskMark monochrome className="pointer-events-none absolute -right-24 -bottom-24 size-[420px] text-white/[0.03]" />
      </aside>

      <main className="flex flex-col justify-center px-6 py-12 sm:px-12">
        <div className="mx-auto w-full max-w-sm">
          <BotdeskLockup className="mb-10 lg:hidden" />
          {children}
        </div>
      </main>
    </div>
  );
}
