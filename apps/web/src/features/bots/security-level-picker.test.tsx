import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderUI } from "@/test/render";
import { SecurityLevelPicker } from "./security-level-picker";

describe("SecurityLevelPicker", () => {
  it("offers every level when the organization has no ceiling", () => {
    renderUI(<SecurityLevelPicker value="ask-before-acting" onChange={vi.fn()} />);
    for (const name of [/^Read only/, /^Ask before acting/, /^Autonomous/]) expect(screen.getByRole("radio", { name })).toBeEnabled();
  });

  it("shows levels above the ceiling as unavailable, and says why", async () => {
    const onChange = vi.fn();
    const { user } = renderUI(<SecurityLevelPicker value="read-only" onChange={onChange} max="ask-before-acting" />);

    const autonomous = screen.getByRole("radio", { name: /^Autonomous/ });
    expect(autonomous).toBeDisabled();
    expect(autonomous).toHaveAccessibleDescription(/Above your organization's highest level \(Ask before acting\)/);
    expect(screen.getByRole("radio", { name: /^Ask before acting/ })).toBeEnabled();

    await user.click(autonomous);
    expect(onChange).not.toHaveBeenCalled();
    await user.click(screen.getByRole("radio", { name: /^Ask before acting/ }));
    expect(onChange).toHaveBeenCalledWith("ask-before-acting");
  });

  it("a bot already above a lowered ceiling keeps showing its level and can move down", async () => {
    const onChange = vi.fn();
    const { user } = renderUI(<SecurityLevelPicker value="autonomous" onChange={onChange} max="read-only" />);
    expect(screen.getByRole("radio", { name: /^Autonomous/ })).toBeChecked();
    await user.click(screen.getByRole("radio", { name: /^Read only/ }));
    expect(onChange).toHaveBeenCalledWith("read-only");
  });

  it("two pickers on one page keep their own names and ids", () => {
    renderUI(
      <>
        <SecurityLevelPicker value="read-only" onChange={vi.fn()} />
        <SecurityLevelPicker label="Highest security level" value="autonomous" onChange={vi.fn()} />
      </>,
    );
    expect(screen.getByRole("radiogroup", { name: "Security level" })).toBeInTheDocument();
    expect(screen.getByRole("radiogroup", { name: "Highest security level" })).toBeInTheDocument();
    expect(screen.getAllByRole("radio", { name: /^Autonomous/ }).map((r) => r.id)).toEqual(["security-autonomous", "highest-security-level-autonomous"]);
  });
});
