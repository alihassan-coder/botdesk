import { createElement, type ComponentProps, type JSX } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock, CodeBlockActions, CodeBlockContent, CodeBlockCopyButton, CodeBlockHeader, CodeBlockLine, CodeBlockTitle } from "@/components/ui/code-block";
import { useHighlightedCode } from "@/hooks/use-highlighted-code";
import { remarkMentions } from "@/lib/remark-mentions";

const REMARK_PLUGINS = [remarkGfm, remarkMentions];

/** The text inside a hast node: a fenced code block's code, as written. */
type HastNode = { type: string; value?: string; children?: HastNode[]; properties?: { className?: unknown } };
const textOf = (node?: HastNode): string => (node?.type === "text" ? (node.value ?? "") : (node?.children ?? []).map(textOf).join(""));

function FencedCode({ node }: ComponentProps<"pre"> & { node?: HastNode }) {
  const code = node?.children?.find((child) => child.type === "element");
  const language = [code?.properties?.className]
    .flat()
    .find((name): name is string => typeof name === "string" && name.startsWith("language-"))
    ?.slice("language-".length);
  const text = textOf(code).replace(/\n$/, "");
  // Coloured once the language loads (plain lines until then, or for a language we don't know);
  // while a reply streams, only the new lines are coloured.
  const lines = useHighlightedCode(text, language ?? "");
  return (
    <CodeBlock size="sm" className="bg-background">
      <CodeBlockHeader>
        <CodeBlockTitle className="font-mono">{language ?? "code"}</CodeBlockTitle>
        <CodeBlockActions>
          <CodeBlockCopyButton value={text} aria-label="Copy code" />
        </CodeBlockActions>
      </CodeBlockHeader>
      <CodeBlockContent>
        {lines.map((line, i) => (
          <CodeBlockLine key={i}>{line}</CodeBlockLine>
        ))}
      </CodeBlockContent>
    </CodeBlock>
  );
}

/** react-markdown hands each component its tree node as `node`; DOM elements mustn't get it. */
function withoutNode<P extends { node?: unknown }>(props: P): Omit<P, "node"> {
  const rest = { ...props };
  delete rest.node;
  return rest;
}

/** A markdown element shown as `tag`, with BotDesk's classes. */
function styled<T extends keyof JSX.IntrinsicElements>(tag: T, className: string) {
  return function Styled(props: ComponentProps<T> & { node?: unknown }) {
    return createElement(tag, { ...withoutNode(props), className });
  };
}

const LINK = "font-medium text-brand underline underline-offset-2";

// Sizes stay close to the 14px body: a chat reply is not a document, so headings only step up a little.
const COMPONENTS: Components = {
  pre: FencedCode,
  code: styled("code", "rounded bg-foreground/[0.07] px-1 py-px font-mono text-[0.86em]"),
  a: (props) => <a {...withoutNode(props)} target="_blank" rel="noopener noreferrer nofollow" className={LINK} />,
  // Bots can link images from anywhere; a link avoids loading (and being tracked by) unknown servers.
  img: ({ src, alt }) =>
    typeof src === "string" ? (
      <a href={src} target="_blank" rel="noopener noreferrer nofollow" className={LINK}>
        {alt || "Image"}
      </a>
    ) : null,
  h1: styled("h3", "text-base font-semibold"),
  h2: styled("h4", "text-[15px] font-semibold"),
  h3: styled("h5", "font-semibold"),
  h4: styled("h6", "font-semibold"),
  h5: styled("h6", "font-semibold"),
  h6: styled("h6", "font-semibold"),
  ul: styled("ul", "list-disc space-y-1 pl-5 marker:text-muted-foreground"),
  ol: styled("ol", "list-decimal space-y-1 pl-5 marker:text-muted-foreground"),
  li: styled("li", "pl-0.5 has-[>input]:-ml-5 has-[>input]:list-none [&>p+p]:mt-1.5"),
  input: styled("input", "mr-1.5 align-middle accent-brand"),
  blockquote: styled("blockquote", "border-l-2 border-foreground/15 pl-3 text-muted-foreground"),
  hr: styled("hr", "border-foreground/10"),
  table: (props) => (
    <div className="max-w-full overflow-x-auto rounded-lg border border-foreground/10 bg-background">
      <table {...withoutNode(props)} className="w-full border-collapse text-[13px]" />
    </div>
  ),
  th: styled("th", "border-b border-foreground/10 px-2.5 py-1.5 text-left font-semibold"),
  td: styled("td", "border-t border-foreground/5 px-2.5 py-1.5 align-top"),
};

/**
 * A bot's reply as formatted markdown (GitHub flavour: tables, task lists, strikethrough).
 * Raw HTML in the text is never rendered, and react-markdown drops unsafe link targets (`javascript:`).
 */
export function MarkdownText({ text }: { text: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-2.5">
      <Markdown remarkPlugins={REMARK_PLUGINS} components={COMPONENTS}>
        {text}
      </Markdown>
    </div>
  );
}
