import type { CSSProperties } from "react";

type SplitTextProps = {
  text: string;
  className?: string;
  delayMs?: number;
};

export function SplitText({ text, className, delayMs = 42 }: SplitTextProps) {
  return (
    <span className={className} aria-label={text}>
      {text.split("").map((character, index) => (
        <span
          aria-hidden="true"
          className="split-pop-letter"
          key={`${character}-${index}`}
          style={{ animationDelay: `${index * delayMs}ms` } as CSSProperties}
        >
          {character === " " ? "\u00A0" : character}
        </span>
      ))}
    </span>
  );
}
