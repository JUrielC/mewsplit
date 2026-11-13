export function Logo() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden>
      <path d="M2 3h16M5 8h10M8 13h4" stroke="var(--text)" strokeWidth="2" strokeLinecap="round" fill="none" />
      <path d="M10 13v5" stroke="var(--hue)" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function FileIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path d="M6 3h8l4 4v14H6z" />
      <path d="M14 3v4h4M12 11v6M9.5 14.5 12 17l2.5-2.5" />
    </svg>
  );
}

export function AlertIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 4.8v3.8M8 10.8v.4" />
    </svg>
  );
}
