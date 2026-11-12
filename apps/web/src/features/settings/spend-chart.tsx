import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { formatUsd } from "@/lib/format";
import type { UsageDay } from "@/data/types";

/*
 * Two series, colours validated with the dataviz palette checker (light and dark pass
 * lightness, chroma, colour-blind separation and contrast). Text never uses series colours.
 */
const config = {
  tokensUsd: { label: "Models", theme: { light: "#3B30FF", dark: "#7B73FF" } },
  computerUsd: { label: "Computers", theme: { light: "#14A38B", dark: "#22A88F" } },
} satisfies ChartConfig;

/** Dates are plain days ("2026-11-12"); read them in UTC so every timezone shows the same label. */
const dayLabel = (date: string) =>
  new Date(`${date}T00:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

/** Daily spend for the last 14 days, split into model tokens and computer time. */
export function SpendChart({ usage }: { usage: UsageDay[] }) {
  return (
    <figure>
      <ChartContainer config={config} className="h-64 w-full">
        <BarChart data={usage} margin={{ left: 0, right: 0, top: 8 }} barCategoryGap="30%">
          <CartesianGrid vertical={false} strokeOpacity={0.5} />
          <XAxis dataKey="date" tickFormatter={dayLabel} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={24} />
          <YAxis tickFormatter={(v: number) => `$${v}`} tickLine={false} axisLine={false} width={36} />
          <ChartTooltip cursor={{ fillOpacity: 0.06 }} content={<ChartTooltipContent labelFormatter={(_, items) => dayLabel(String(items?.[0]?.payload?.date ?? ""))} />} />
          <ChartLegend content={<ChartLegendContent />} />
          {/* A 2px gap between the stacked segments (stroke in the page colour) keeps them distinct. */}
          <Bar dataKey="computerUsd" stackId="spend" fill="var(--color-computerUsd)" stroke="var(--background)" strokeWidth={2} />
          <Bar dataKey="tokensUsd" stackId="spend" fill="var(--color-tokensUsd)" stroke="var(--background)" strokeWidth={2} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ChartContainer>

      {/* The same numbers as a table, for screen readers. */}
      <table className="sr-only">
        <caption>Daily spend, last 14 days</caption>
        <thead>
          <tr><th>Day</th><th>Models</th><th>Computers</th></tr>
        </thead>
        <tbody>
          {usage.map((d) => (
            <tr key={d.date}><td>{dayLabel(d.date)}</td><td>{formatUsd(d.tokensUsd)}</td><td>{formatUsd(d.computerUsd)}</td></tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
