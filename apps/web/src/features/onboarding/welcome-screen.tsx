"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useAuthStatus, useCurrentUser, useIsDemo, useOrg } from "@/data/store";
import { BotdeskLockup } from "@/features/shell/logo";
import { markOnboardingDone } from "./done-flag";
import { BotStep } from "./bot-step";
import { GmailStep } from "./gmail-step";
import { KeyStep } from "./key-step";
import { OrgStep } from "./org-step";
import { SetupProgress } from "./setup-progress";

export const SETUP_STEPS = ["Organization", "AI key", "First bot", "Gmail"];

/**
 * /welcome — first-time setup for the owner of a new organization: name it, add an AI key, hire
 * a first bot, connect Gmail. Every step can be skipped. Finishing (or skipping it all) is
 * remembered for this org and opens the first bot's DM, or home if none was hired.
 */
export function WelcomeScreen() {
  const router = useRouter();
  const signedIn = useAuthStatus() === "signed-in";
  const role = useCurrentUser()?.role;
  const demo = useIsDemo();
  const allowed = role === "owner" && !demo;
  const org = useOrg();
  const [step, setStep] = useState(0);
  const [threadId, setThreadId] = useState<string | null>(null);

  // Setup is the owner's job, and the demo is already set up: anyone else goes into the app.
  useEffect(() => {
    if (signedIn && !allowed) router.replace("/");
  }, [signedIn, allowed, router]);

  // The page renders (hidden) before sign-in; the steps need the org, so they wait for it.
  if (!signedIn || !allowed) return null;

  const markDone = () => markOnboardingDone(org.id);
  const finish = () => {
    markDone();
    router.replace(threadId ? `/chat/${threadId}` : "/");
  };
  const next = () => setStep((s) => s + 1);

  return (
    <div className="min-h-svh bg-background">
      <header className="mx-auto flex h-16 w-full max-w-2xl items-center justify-between px-4">
        <BotdeskLockup />
        <Button variant="ghost" size="sm" onClick={finish} className="text-muted-foreground">Skip setup</Button>
      </header>
      <main className="mx-auto flex w-full max-w-2xl flex-col gap-10 px-4 pt-6 pb-16 sm:pt-12">
        <SetupProgress steps={SETUP_STEPS} current={step} />
        {/* key: each step starts fresh, and the org step picks up the current name. */}
        <div key={step}>
          {step === 0 && <OrgStep key={org.id} onNext={next} />}
          {step === 1 && <KeyStep onNext={next} />}
          {step === 2 && <BotStep onNext={next} onHired={(id) => setThreadId((t) => t ?? id)} onLeave={markDone} />}
          {step === 3 && <GmailStep onFinish={finish} onLeave={markDone} />}
        </div>
      </main>
    </div>
  );
}
