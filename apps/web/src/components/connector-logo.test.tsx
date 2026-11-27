import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConnectorLogo, isNearBlack } from "./connector-logo";

describe("ConnectorLogo", () => {
  it("draws a known connector's brand mark, labelled with its name", () => {
    render(<ConnectorLogo connectorId="gmail" name="Gmail" />);
    const logo = screen.getByRole("img", { name: "Gmail" });
    expect(logo).toHaveAttribute("data-logo", "brand");
    const svg = logo.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg!.style.getPropertyValue("--logo-color")).toBe("#EA4335");
    expect(svg!.querySelector("path")?.getAttribute("d")).toBeTruthy();
  });

  it("falls back to the name's initial for an unknown id", () => {
    render(<ConnectorLogo connectorId="acme-crm" name="Acme CRM" />);
    const logo = screen.getByRole("img", { name: "Acme CRM" });
    expect(logo).toHaveAttribute("data-logo", "fallback");
    expect(logo).toHaveTextContent("A");
    expect(logo.querySelector("path[d]")).toBeNull();
  });

  it("keeps the neutral icon for the demo plugin and brands simple-icons lacks", () => {
    for (const [id, name] of [["demo", "Demo"], ["slack", "Slack"], ["mcp", "Custom MCP server"]]) {
      render(<ConnectorLogo connectorId={id} name={name} />);
      const logo = screen.getByRole("img", { name });
      expect(logo).toHaveAttribute("data-logo", "fallback");
      expect(logo.querySelector("svg")).not.toBeNull(); // a lucide icon
    }
  });

  it("draws the catalogue's MCP servers' marks, Jira's for Atlassian", () => {
    for (const [id, name] of [["google-drive", "Google Drive"], ["atlassian", "Jira & Confluence"], ["sentry", "Sentry"], ["asana", "Asana"]]) {
      render(<ConnectorLogo connectorId={id} name={name} />);
      expect(screen.getByRole("img", { name })).toHaveAttribute("data-logo", "brand");
    }
  });

  it("prefers the picture it's given over the brand mark, but only an inline one", () => {
    const icon = "data:image/png;base64,iVBORw0KGgo=";
    const { container, rerender } = render(<ConnectorLogo connectorId="linear" name="Linear" iconUrl={icon} />);
    expect(screen.getByRole("img", { name: "Linear" })).toHaveAttribute("data-logo", "icon");
    expect(container.querySelector("img")).toHaveAttribute("src", icon);
    expect(container.querySelector("img")).toHaveAttribute("alt", "");

    rerender(<ConnectorLogo connectorId="linear" name="Linear" iconUrl="https://tracker.example/pixel.png" />);
    expect(screen.getByRole("img", { name: "Linear" })).toHaveAttribute("data-logo", "brand");
    expect(container.querySelector("img")).toBeNull();
  });

  it("switches a near-black brand colour to the foreground colour in dark mode", () => {
    render(
      <>
        <ConnectorLogo connectorId="github" name="GitHub" />
        <ConnectorLogo connectorId="gmail" name="Gmail" />
      </>,
    );
    expect(screen.getByRole("img", { name: "GitHub" }).querySelector("svg")).toHaveClass("dark:text-foreground");
    expect(screen.getByRole("img", { name: "Gmail" }).querySelector("svg")).not.toHaveClass("dark:text-foreground");
  });

  it("hides itself from screen readers when the name sits next to it", () => {
    const { container } = render(<ConnectorLogo connectorId="gmail" name="Gmail" decorative />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
  });
});

describe("isNearBlack", () => {
  it("flags blacks and near-blacks only", () => {
    expect(isNearBlack("181717")).toBe(true);
    expect(isNearBlack("#000000")).toBe(true);
    expect(isNearBlack("362D59")).toBe(true); // Sentry's deep purple
    expect(isNearBlack("0052CC")).toBe(false);
    expect(isNearBlack("EA4335")).toBe(false);
    expect(isNearBlack("5E6AD2")).toBe(false);
    expect(isNearBlack("nope")).toBe(false);
  });
});
