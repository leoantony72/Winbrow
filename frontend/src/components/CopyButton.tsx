import { useState, type MouseEvent } from "react";

/** Copy text via the async clipboard API with a document.execCommand fallback. */
export async function writeClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to the legacy path (insecure context, permission denial).
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(area);
    return copied;
  } catch {
    return false;
  }
}

interface CopyButtonProps {
  text: string;
  title?: string;
  className?: string;
  /** Keep the click from toggling an enclosing <details>/row. */
  stopPropagation?: boolean;
}

export default function CopyButton({
  text,
  title = "Copy to clipboard",
  className = "answer-copy",
  stopPropagation = false,
}: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const onClick = async (event: MouseEvent<HTMLButtonElement>) => {
    if (stopPropagation) {
      event.preventDefault();
      event.stopPropagation();
    }
    if (await writeClipboard(text)) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    }
  };

  return (
    <button
      type="button"
      className={className}
      onClick={onClick}
      title={title}
      aria-label={title}
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}
