"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Plus, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { actions, useTemplates } from "@/data/store";
import { PageHeader } from "@/features/shell/page-header";
import { TemplateCard } from "./template-card";

/** /marketplace — ready-made bots you hire in one click, or build your own. */
export function MarketplaceScreen() {
  const router = useRouter();
  const templates = useTemplates();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");

  const categories = ["All", ...new Set(templates.map((t) => t.category))];
  const q = query.trim().toLowerCase();
  const shown = templates
    .filter((t) => category === "All" || t.category === category)
    .filter((t) => !q || `${t.name} ${t.role} ${t.description}`.toLowerCase().includes(q))
    .sort((a, b) => b.installs - a.installs);

  async function hire(templateId: string, name: string) {
    const result = await actions.createBotFromTemplate(templateId);
    if (!result.ok) return void toast.error(result.error);
    toast.success(`${name} joined your team.`);
    router.push(`/chat/${result.threadId}`);
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Marketplace" />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 p-4 md:p-8">
          <section className="flex flex-col gap-4">
            <div>
              <h2 className="text-3xl font-semibold tracking-tight">Hire a teammate</h2>
              <p className="mt-1 text-muted-foreground">Ready-made bots with the right tools and safe defaults. Change anything after you hire.</p>
            </div>
            <div className="relative max-w-xl">
              <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search bots" aria-label="Search bots" className="h-11 rounded-full pl-10" />
            </div>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Categories">
              {categories.map((c) => (
                <button
                  key={c}
                  type="button"
                  aria-pressed={category === c}
                  onClick={() => setCategory(c)}
                  className={cn(
                    "rounded-full border px-3.5 py-1.5 text-sm transition-colors",
                    category === c ? "border-foreground bg-foreground text-background" : "hover:bg-muted",
                  )}
                >
                  {c}
                </button>
              ))}
            </div>
          </section>

          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-label="Bots you can hire">
            {shown.map((t) => (
              <TemplateCard key={t.id} template={t} onHire={() => hire(t.id, t.name)} />
            ))}
            <Link
              href="/bots/new"
              className="flex min-h-48 flex-col items-center justify-center gap-2 rounded-2xl border border-dashed p-5 text-center text-muted-foreground transition-colors hover:border-foreground/40 hover:text-foreground"
            >
              <Plus className="size-6" />
              <span className="font-medium">Build your own</span>
              <span className="text-sm">Name it, give it a job, set its limits.</span>
            </Link>
          </section>

          {shown.length === 0 && <p className="text-center text-sm text-muted-foreground">No bots match. Try another word, or build your own.</p>}
        </div>
      </div>
    </div>
  );
}
