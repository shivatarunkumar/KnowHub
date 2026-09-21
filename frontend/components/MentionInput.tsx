"use client";

import { type KeyboardEvent, useEffect, useRef, useState } from "react";

type Person = { id: string; display_name: string; handle: string };

/**
 * Textarea that suggests colleagues while you type "@". Picking one inserts their
 * handle, and the API notifies anyone mentioned when the comment is posted.
 */
export function MentionInput({
  value,
  onChange,
  onSubmit,
  placeholder,
  rows = 1,
  autoFocus = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit?: () => void;
  placeholder?: string;
  rows?: number;
  autoFocus?: boolean;
}) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [query, setQuery] = useState<string | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [active, setActive] = useState(0);

  // the "@word" immediately before the caret, if any
  function mentionAtCaret(text: string, caret: number): string | null {
    const before = text.slice(0, caret);
    const match = /(?:^|\s)@([a-zA-Z0-9_.-]*)$/.exec(before); // never mid-word, so emails are ignored
    return match ? match[1] : null;
  }

  useEffect(() => {
    if (query === null || query.length < 1) {
      setPeople([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/v1/users/search?q=${encodeURIComponent(query)}`);
        if (res.ok) {
          setPeople(await res.json());
          setActive(0);
        }
      } catch {
        setPeople([]);
      }
    }, 150);
    return () => clearTimeout(timer);
  }, [query]);

  function choose(person: Person) {
    const input = inputRef.current;
    if (!input) return;
    const caret = input.selectionStart ?? value.length;
    const before = value.slice(0, caret).replace(/@([a-zA-Z0-9_.-]*)$/, `@${person.handle} `);
    const next = before + value.slice(caret);
    onChange(next);
    setQuery(null);
    setPeople([]);
    requestAnimationFrame(() => {
      input.focus();
      input.setSelectionRange(before.length, before.length);
    });
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (people.length > 0) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActive((active + 1) % people.length);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActive((active - 1 + people.length) % people.length);
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        choose(people[active]);
        return;
      }
      if (event.key === "Escape") {
        setPeople([]);
        setQuery(null);
        return;
      }
    }
    // plain Enter sends, Shift+Enter makes a new line
    if (event.key === "Enter" && !event.shiftKey && onSubmit) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <div className="relative">
      <textarea
        ref={inputRef}
        value={value}
        autoFocus={autoFocus}
        rows={rows}
        placeholder={placeholder}
        onChange={(event) => {
          onChange(event.target.value);
          setQuery(mentionAtCaret(event.target.value, event.target.selectionStart ?? 0));
        }}
        onKeyDown={onKeyDown}
        onBlur={() => setTimeout(() => setPeople([]), 150)}
        className="w-full resize-none rounded-lg border border-line bg-bg px-3 py-2 text-sm outline-none focus:border-brand"
      />

      {people.length > 0 && (
        <ul
          role="listbox"
          className="absolute left-0 top-full z-30 mt-1 max-h-56 w-72 overflow-y-auto rounded-xl border border-line bg-bg py-1 shadow-xl"
        >
          {people.map((person, index) => (
            <li key={person.id}>
              <button
                type="button"
                role="option"
                aria-selected={index === active}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(person)}
                onMouseEnter={() => setActive(index)}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm ${
                  index === active ? "bg-surface-hover" : ""
                }`}
              >
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand text-xs font-semibold text-brand-contrast">
                  {person.display_name.charAt(0).toUpperCase()}
                </span>
                <span className="truncate">{person.display_name}</span>
                <span className="truncate text-xs text-muted">@{person.handle}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Renders @handles in a comment as links to that person's channel. */
export function CommentBody({ body }: { body: string }) {
  // same rule as the API: an @ preceded by a word character is part of an email address
  const parts = body.split(/((?<![\w.])@[a-z0-9][a-z0-9_.-]{2,29})/gi);
  return (
    <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">
      {parts.map((part, index) =>
        part.startsWith("@") ? (
          <a key={index} href={`/${part}`} className="font-medium text-brand hover:underline">
            {part}
          </a>
        ) : (
          part
        ),
      )}
    </p>
  );
}
