import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getStoreSnapshot as state } from "@/data/store";
import type { Message } from "@/data/types";
import { renderUI } from "@/test/render";
import { CONTINUE, LimitStopNotice, stoppedAtLimit } from "./limit-stop-notice";

const stopped = (threadId: string, botId: string, errorCode?: Message["errorCode"]): Message => ({
  id: `m-${threadId}`, threadId, author: { type: "bot", id: botId }, parts: [{ type: "text", text: "Half done" }],
  status: "error", error: "This run reached its limit of 25 model steps.", errorCode, createdAt: "2026-11-27T10:00:00Z",
});

describe("a reply stopped at its limit", () => {
  it("is known by its code, or by its words after a reload; other failures aren't", () => {
    const sales = state().threads.find((t) => t.id === "t_sales")!;
    expect(stoppedAtLimit(stopped(sales.id, sales.botId!, "limit"))).toBe(true);
    expect(stoppedAtLimit(stopped(sales.id, sales.botId!))).toBe(true);
    expect(stoppedAtLimit({ ...stopped(sales.id, sales.botId!), error: "This run reached its time limit of 15 minutes." })).toBe(true);
    expect(stoppedAtLimit({ ...stopped(sales.id, sales.botId!), error: "The model didn't answer." })).toBe(false);
  });

  it("Continue asks the bot to carry on", async () => {
    const sales = state().threads.find((t) => t.id === "t_sales")!;
    const { user } = renderUI(<LimitStopNotice message={stopped(sales.id, sales.botId!, "limit")} />);
    expect(screen.getByText(/stopped at its limit/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue" }));
    const last = state().messages.filter((m) => m.threadId === sales.id && m.author.type === "user").at(-1)!;
    expect(last.parts[0]).toEqual({ type: "text", text: CONTINUE });
  });

  it("in a group, Continue names the bot so it's the one that carries on", async () => {
    const group = state().threads.find((t) => t.kind === "group")!;
    const bot = state().bots.find((b) => group.participants.some((p) => p.type === "bot" && p.id === b.id))!;
    const { user } = renderUI(<LimitStopNotice message={stopped(group.id, bot.id, "limit")} />);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    const last = state().messages.filter((m) => m.threadId === group.id && m.author.type === "user").at(-1)!;
    expect(last.parts[0]).toEqual({ type: "text", text: `@${bot.handle} ${CONTINUE}` });
  });
});
