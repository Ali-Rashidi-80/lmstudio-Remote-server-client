"use client";

import { Fragment, ReactNode, useState } from "react";

function isSafeHref(href: string): boolean {
  const trimmed = href.trim().toLowerCase();
  return (
    trimmed.startsWith("https://") ||
    trimmed.startsWith("http://") ||
    trimmed.startsWith("/")
  );
}

function renderInline(line: string, keyPrefix: string): ReactNode[] {
  const pattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*|\[[^\]\n]+\]\([^)\n]+\))/g;
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let idx = 0;

  while ((match = pattern.exec(line)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(line.slice(lastIndex, match.index));
    }
    const token = match[0];
    const k = `${keyPrefix}-${idx++}`;
    if (token.startsWith("`") && token.endsWith("`")) {
      nodes.push(
        <code key={k} className="inline-code">
          {token.slice(1, -1)}
        </code>
      );
    } else if (token.startsWith("**") && token.endsWith("**")) {
      nodes.push(<strong key={k}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("*") && token.endsWith("*")) {
      nodes.push(<em key={k}>{token.slice(1, -1)}</em>);
    } else if (token.startsWith("[")) {
      const split = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (split && isSafeHref(split[2])) {
        nodes.push(
          <a key={k} href={split[2]} target="_blank" rel="noopener noreferrer">
            {split[1]}
          </a>
        );
      } else {
        nodes.push(token);
      }
    }
    lastIndex = match.index + token.length;
  }

  if (lastIndex < line.length) {
    nodes.push(line.slice(lastIndex));
  }
  return nodes;
}

function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false);

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="code-block" dir="ltr">
      <div className="code-block-head">
        <span>{lang || "text"}</span>
        <button type="button" className="btn btn-xs" onClick={onCopy}>
          {copied ? "کپی شد" : "کپی"}
        </button>
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
}

function renderProse(segment: string, baseKey: string): ReactNode {
  const lines = segment.split("\n");
  const blocks: ReactNode[] = [];
  let listItems: ReactNode[] = [];
  let listOrdered = false;

  const flushList = (key: string) => {
    if (!listItems.length) return;
    if (listOrdered) {
      blocks.push(
        <ol key={key} className="md-list">
          {listItems}
        </ol>
      );
    } else {
      blocks.push(
        <ul key={key} className="md-list">
          {listItems}
        </ul>
      );
    }
    listItems = [];
  };

  lines.forEach((rawLine, i) => {
    const line = rawLine;
    const trimmed = line.trim();
    const k = `${baseKey}-l${i}`;

    if (!trimmed) {
      flushList(`${k}-flush`);
      return;
    }

    const bullet = trimmed.match(/^[-*]\s+(.+)$/);
    const ordered = trimmed.match(/^\d+\.\s+(.+)$/);
    if (bullet) {
      if (listItems.length && listOrdered) flushList(`${k}-switch`);
      listOrdered = false;
      listItems.push(<li key={k}>{renderInline(bullet[1], k)}</li>);
      return;
    }
    if (ordered) {
      if (listItems.length && !listOrdered) flushList(`${k}-switch`);
      listOrdered = true;
      listItems.push(<li key={k}>{renderInline(ordered[1], k)}</li>);
      return;
    }

    flushList(`${k}-end`);
    if (trimmed.startsWith("### ")) {
      blocks.push(
        <h4 key={k} className="md-h">
          {renderInline(trimmed.slice(4), k)}
        </h4>
      );
    } else if (trimmed.startsWith("## ")) {
      blocks.push(
        <h3 key={k} className="md-h">
          {renderInline(trimmed.slice(3), k)}
        </h3>
      );
    } else if (trimmed.startsWith("# ")) {
      blocks.push(
        <h2 key={k} className="md-h">
          {renderInline(trimmed.slice(2), k)}
        </h2>
      );
    } else {
      blocks.push(
        <p key={k} className="md-p">
          {renderInline(line, k)}
        </p>
      );
    }
  });

  flushList(`${baseKey}-tail`);
  return <Fragment key={baseKey}>{blocks}</Fragment>;
}

export function MarkdownContent({
  content,
  streaming = false,
}: {
  content: string;
  streaming?: boolean;
}) {
  if (!content) return null;
  const fenceCount = (content.match(/```/g) || []).length;
  const normalized = streaming && fenceCount % 2 !== 0 ? `${content}\n\`\`\`` : content;

  const segments: ReactNode[] = [];
  const codeFence = /```([a-zA-Z0-9_+#.-]*)\n([\s\S]*?)```/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let idx = 0;

  while ((match = codeFence.exec(normalized)) !== null) {
    if (match.index > last) {
      segments.push(renderProse(normalized.slice(last, match.index), `p-${idx++}`));
    }
    segments.push(
      <CodeBlock key={`c-${idx++}`} lang={match[1]} code={match[2].replace(/\n$/, "")} />
    );
    last = match.index + match[0].length;
  }

  if (last < normalized.length) {
    segments.push(renderProse(normalized.slice(last), `p-${idx++}`));
  }

  return <div className="md-body">{segments}</div>;
}
