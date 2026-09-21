/**
 * Small SVG building blocks shared by the About diagrams.
 *
 * Everything is drawn with our CSS variables rather than fixed colours, so the diagrams
 * follow light and dark mode, and every diagram scales with its container (viewBox +
 * width 100%) instead of scrolling sideways on a phone.
 */

type Tone = "brand" | "plain" | "store" | "ghost";

const FILL: Record<Tone, string> = {
  brand: "var(--brand)",
  plain: "var(--surface)",
  store: "var(--surface)",
  ghost: "transparent",
};

const STROKE: Record<Tone, string> = {
  brand: "var(--brand)",
  plain: "var(--border)",
  store: "var(--brand)",
  ghost: "var(--border)",
};

export function Box({
  x,
  y,
  w,
  h,
  title,
  lines = [],
  tone = "plain",
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  title: string;
  lines?: string[];
  tone?: Tone;
}) {
  const textColor = tone === "brand" ? "var(--brand-contrast)" : "var(--text)";
  const subColor = tone === "brand" ? "var(--brand-contrast)" : "var(--muted)";
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={10}
        fill={FILL[tone]}
        stroke={STROKE[tone]}
        strokeWidth={tone === "store" ? 1.5 : 1}
        strokeDasharray={tone === "ghost" ? "4 3" : undefined}
      />
      <text x={x + w / 2} y={y + 20} textAnchor="middle" fontSize={13} fontWeight={600} fill={textColor}>
        {title}
      </text>
      {lines.map((line, i) => (
        <text
          key={line}
          x={x + w / 2}
          y={y + 38 + i * 15}
          textAnchor="middle"
          fontSize={11}
          fill={subColor}
          opacity={tone === "brand" ? 0.9 : 1}
        >
          {line}
        </text>
      ))}
    </g>
  );
}

export function Arrow({
  from,
  to,
  label,
  dashed = false,
  labelAbove = true,
  accent = false,
}: {
  from: [number, number];
  to: [number, number];
  label?: string;
  dashed?: boolean;
  labelAbove?: boolean;
  accent?: boolean;
}) {
  const [x1, y1] = from;
  const [x2, y2] = to;
  const color = accent ? "var(--brand)" : "var(--muted)";
  return (
    <g>
      <line
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        stroke={color}
        strokeWidth={accent ? 1.8 : 1.2}
        strokeDasharray={dashed ? "5 4" : undefined}
        markerEnd={accent ? "url(#arrow-accent)" : "url(#arrow)"}
      />
      {label && (
        <text
          x={(x1 + x2) / 2}
          y={(y1 + y2) / 2 + (labelAbove ? -6 : 14)}
          textAnchor="middle"
          fontSize={10.5}
          fill={color}
        >
          {label}
        </text>
      )}
    </g>
  );
}

/** Arrowheads, defined once per diagram. */
export function Defs() {
  return (
    <defs>
      {[
        ["arrow", "var(--muted)"],
        ["arrow-accent", "var(--brand)"],
      ].map(([id, color]) => (
        <marker
          key={id}
          id={id}
          viewBox="0 0 10 10"
          refX={9}
          refY={5}
          markerWidth={6}
          markerHeight={6}
          orient="auto-start-reverse"
        >
          <path d="M0 0 L10 5 L0 10 z" fill={color} />
        </marker>
      ))}
    </defs>
  );
}

/** A vertical lifeline for the sequence diagrams, with a header box. */
export function Lane({
  x,
  label,
  sub,
  top,
  bottom,
}: {
  x: number;
  label: string;
  sub?: string;
  top: number;
  bottom: number;
}) {
  return (
    <g>
      <rect x={x - 70} y={top} width={140} height={sub ? 42 : 30} rx={8} fill="var(--surface)" stroke="var(--border)" />
      <text x={x} y={top + 19} textAnchor="middle" fontSize={12.5} fontWeight={600} fill="var(--text)">
        {label}
      </text>
      {sub && (
        <text x={x} y={top + 34} textAnchor="middle" fontSize={10} fill="var(--muted)">
          {sub}
        </text>
      )}
      <line
        x1={x}
        y1={top + (sub ? 42 : 30)}
        x2={x}
        y2={bottom}
        stroke="var(--border)"
        strokeWidth={1}
        strokeDasharray="4 4"
      />
    </g>
  );
}

/** One numbered step of a sequence: an arrow between two lanes with a caption. */
export function Step({
  n,
  fromX,
  toX,
  y,
  label,
  note,
  accent = false,
  dashed = false,
}: {
  n: number;
  fromX: number;
  toX: number;
  y: number;
  label: string;
  note?: string;
  accent?: boolean;
  dashed?: boolean;
}) {
  const forward = toX > fromX;
  const labelX = (fromX + toX) / 2;
  return (
    <g>
      <circle cx={fromX + (forward ? -22 : 22)} cy={y} r={9} fill="var(--brand)" />
      <text
        x={fromX + (forward ? -22 : 22)}
        y={y + 3.5}
        textAnchor="middle"
        fontSize={10}
        fontWeight={700}
        fill="var(--brand-contrast)"
      >
        {n}
      </text>
      <Arrow from={[fromX, y]} to={[toX, y]} accent={accent} dashed={dashed} />
      <text x={labelX} y={y - 7} textAnchor="middle" fontSize={11.5} fill="var(--text)">
        {label}
      </text>
      {note && (
        <text x={labelX} y={y + 15} textAnchor="middle" fontSize={10} fill="var(--muted)">
          {note}
        </text>
      )}
    </g>
  );
}

/** Wrapper: a titled figure with the SVG scaled to its container. */
export function Figure({
  title,
  caption,
  viewBox,
  children,
}: {
  title: string;
  caption?: string;
  viewBox: string;
  children: React.ReactNode;
}) {
  return (
    <figure className="mt-6 overflow-hidden rounded-xl border border-line bg-bg">
      <figcaption className="border-b border-line bg-surface/60 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
        {title}
      </figcaption>
      <div className="p-3 sm:p-4">
        <svg viewBox={viewBox} className="h-auto w-full" role="img" aria-label={title}>
          <Defs />
          {children}
        </svg>
      </div>
      {caption && <p className="border-t border-line px-4 py-2.5 text-xs text-muted">{caption}</p>}
    </figure>
  );
}
