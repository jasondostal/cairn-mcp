"use client";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useMetricsStream } from "@/hooks/use-metrics-stream";
import { useSidebar } from "@/components/ui/sidebar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Settings2 } from "lucide-react";
import type { MetricsBucket } from "@/lib/api";

// ---------------------------------------------------------------------------
// Metric definitions
// ---------------------------------------------------------------------------

export type MetricKey =
  | "ops_count"
  | "tokens_in"
  | "tokens_out"
  | "latency_avg_ms"
  | "errors"
  | "active_sessions"
  | "cat_reads"
  | "cat_writes"
  | "cat_llm"
  | "cat_embedding"
  | "cat_work"
  | "cat_sessions";

export type DisplayMode = "motes" | "ekg" | "numeric";

interface MetricDef {
  key: MetricKey;
  label: string;
  shortLabel: string;
  color: string;
  format: (v: number) => string;
  group?: "aggregate" | "category";
}

const METRIC_DEFS: MetricDef[] = [
  // Aggregate metrics
  {
    key: "ops_count",
    label: "Operations / sec",
    shortLabel: "ops",
    color: "var(--pulse-ops)",
    format: (v) => v.toString(),
    group: "aggregate",
  },
  {
    key: "tokens_in",
    label: "Tokens in / sec",
    shortLabel: "tok↓",
    color: "var(--pulse-tokens)",
    format: (v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toString()),
    group: "aggregate",
  },
  {
    key: "tokens_out",
    label: "Tokens out / sec",
    shortLabel: "tok↑",
    color: "var(--pulse-tokens)",
    format: (v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toString()),
    group: "aggregate",
  },
  {
    key: "latency_avg_ms",
    label: "Avg latency (ms)",
    shortLabel: "lat",
    color: "var(--pulse-latency)",
    format: (v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${Math.round(v)}ms`),
    group: "aggregate",
  },
  {
    key: "errors",
    label: "Errors / sec",
    shortLabel: "err",
    color: "var(--pulse-errors)",
    format: (v) => v.toString(),
    group: "aggregate",
  },
  {
    key: "active_sessions",
    label: "Active sessions",
    shortLabel: "sess",
    color: "var(--pulse-sessions)",
    format: (v) => v.toString(),
    group: "aggregate",
  },
  // Category metrics
  {
    key: "cat_reads",
    label: "Reads (search, recall)",
    shortLabel: "read",
    color: "var(--pulse-tokens)",
    format: (v) => v.toString(),
    group: "category",
  },
  {
    key: "cat_writes",
    label: "Writes (store, modify)",
    shortLabel: "write",
    color: "var(--pulse-ops)",
    format: (v) => v.toString(),
    group: "category",
  },
  {
    key: "cat_llm",
    label: "LLM calls",
    shortLabel: "llm",
    color: "var(--pulse-sessions)",
    format: (v) => v.toString(),
    group: "category",
  },
  {
    key: "cat_embedding",
    label: "Embeddings",
    shortLabel: "emb",
    color: "var(--pulse-latency)",
    format: (v) => v.toString(),
    group: "category",
  },
  {
    key: "cat_work",
    label: "Work items",
    shortLabel: "work",
    color: "var(--pulse-errors)",
    format: (v) => v.toString(),
    group: "category",
  },
  {
    key: "cat_sessions",
    label: "Sessions",
    shortLabel: "sess",
    color: "var(--pulse-sessions)",
    format: (v) => v.toString(),
    group: "category",
  },
];

const METRIC_MAP = new Map(METRIC_DEFS.map((d) => [d.key, d]));

const LS_METRICS_KEY = "cairn:ekg-metrics";
const LS_POSITION_KEY = "cairn:ekg-position";
const LS_DISPLAY_KEY = "cairn:ekg-display";
const DEFAULT_METRICS: MetricKey[] = ["ops_count", "latency_avg_ms"];
const DEFAULT_DISPLAY: DisplayMode = "motes";
const MAX_SELECTED = 3;

const DISPLAY_MODE_LABELS: Record<DisplayMode, string> = {
  motes: "Motes",
  ekg: "EKG",
  numeric: "Numeric",
};

// Map cat_* keys to by_category dict keys
const CATEGORY_KEY_MAP: Record<string, string> = {
  cat_reads: "reads",
  cat_writes: "writes",
  cat_llm: "llm",
  cat_embedding: "embedding",
  cat_work: "work",
  cat_sessions: "sessions",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function loadSelectedMetrics(): MetricKey[] {
  try {
    const stored = localStorage.getItem(LS_METRICS_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as string[];
      const valid = parsed.filter((k) => METRIC_MAP.has(k as MetricKey)) as MetricKey[];
      if (valid.length > 0) return valid.slice(0, MAX_SELECTED);
    }
  } catch { /* ignore */ }
  return DEFAULT_METRICS;
}

function loadDisplayMode(): DisplayMode {
  try {
    const stored = localStorage.getItem(LS_DISPLAY_KEY);
    if (stored === "motes" || stored === "ekg" || stored === "numeric") return stored;
  } catch { /* ignore */ }
  return DEFAULT_DISPLAY;
}

function extractSeries(buckets: MetricsBucket[], key: MetricKey): { v: number }[] {
  const catKey = CATEGORY_KEY_MAP[key];
  if (catKey) {
    return buckets.map((b) => ({ v: b.by_category?.[catKey] ?? 0 }));
  }
  return buckets.map((b) => ({ v: b[key as keyof MetricsBucket] as number }));
}

function resolveColor(cssVar: string): string {
  const temp = document.createElement("div");
  temp.style.color = cssVar;
  document.body.appendChild(temp);
  const rgb = getComputedStyle(temp).color;
  document.body.removeChild(temp);
  const match = rgb.match(/(\d+),\s*(\d+),\s*(\d+)/);
  return match ? `${match[1]},${match[2]},${match[3]}` : "128,200,128";
}

// ---------------------------------------------------------------------------
// Display: Motes — ambient drifting dots, solid on real events
// ---------------------------------------------------------------------------

interface Mote {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  opacity: number;
  solid: boolean;
  life: number;
  maxLife: number;
}

const AMBIENT_COUNT = 5;
const MOTE_SPEED = 0.25;
const AMBIENT_OPACITY = 0.12;
// Minimum event motes — even 1 op spawns a visible burst
const MIN_EVENT_MOTES = 8;

function spawnAmbient(w: number, h: number): Mote {
  return {
    x: Math.random() * w,
    y: Math.random() * h,
    vx: (Math.random() - 0.5) * MOTE_SPEED,
    vy: (Math.random() - 0.5) * MOTE_SPEED * 0.5,
    r: 0.8 + Math.random() * 0.7,
    opacity: AMBIENT_OPACITY * (0.5 + Math.random() * 0.5),
    solid: false,
    life: 1,
    maxLife: 1,
  };
}

function spawnEvent(w: number, h: number): Mote {
  return {
    x: w * (0.15 + Math.random() * 0.7),
    y: h * (0.1 + Math.random() * 0.8),
    vx: (Math.random() - 0.5) * MOTE_SPEED * 0.5,
    vy: (Math.random() - 0.5) * MOTE_SPEED * 0.3,
    r: 3 + Math.random() * 3,
    opacity: 1.0,
    solid: true,
    life: 1,
    maxLife: 1,
  };
}

function PulseMotes({
  data,
  color,
  height = 20,
}: {
  data: { v: number }[];
  color: string;
  height?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const motesRef = useRef<Mote[]>([]);
  const rafRef = useRef<number>(0);
  const flashRef = useRef(0);

  const resolvedColor = useRef("128,200,128");
  useEffect(() => {
    if (!canvasRef.current) return;
    resolvedColor.current = resolveColor(color);
  }, [color]);

  const sizeRef = useRef({ w: 0, h: 0 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    function resize() {
      if (!canvas || !ctx) return;
      const rect = canvas.getBoundingClientRect();
      const w = Math.round(rect.width);
      const h = Math.round(rect.height);
      if (w === 0 || h === 0) return;
      sizeRef.current = { w, h };
      canvas.width = w * 2;
      canvas.height = h * 2;
      ctx.setTransform(2, 0, 0, 2, 0, 0);
      motesRef.current = [];
      for (let i = 0; i < AMBIENT_COUNT; i++) {
        motesRef.current.push(spawnAmbient(w, h));
      }
    }

    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();

    let running = true;

    function tick() {
      if (!running || !ctx) return;
      const { w, h } = sizeRef.current;
      if (w === 0) { rafRef.current = requestAnimationFrame(tick); return; }
      ctx.clearRect(0, 0, w, h);
      const motes = motesRef.current;
      const c = resolvedColor.current;

      if (flashRef.current > 0) {
        ctx.fillStyle = `rgba(${c}, ${flashRef.current * 0.15})`;
        ctx.fillRect(0, 0, w, h);
        flashRef.current = Math.max(0, flashRef.current - 0.02);
      }

      for (let i = motes.length - 1; i >= 0; i--) {
        const m = motes[i];
        m.x += m.vx;
        m.y += m.vy;
        if (!m.solid) {
          m.vx += (Math.random() - 0.5) * 0.02;
          m.vy += (Math.random() - 0.5) * 0.02;
          m.vx *= 0.99;
          m.vy *= 0.99;
        }
        if (m.solid) {
          m.life -= 0.0015;
          if (m.life <= 0) {
            motes.splice(i, 1);
            continue;
          }
        }
        if (!m.solid) {
          if (m.x < -4) m.x = w + 2;
          if (m.x > w + 4) m.x = -2;
          if (m.y < -4) m.y = h + 2;
          if (m.y > h + 4) m.y = -2;
        }

        const alpha = m.solid ? m.opacity * m.life : m.opacity;

        if (m.solid) {
          ctx.beginPath();
          ctx.arc(m.x, m.y, m.r * 3.5, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(${c}, ${alpha * 0.2})`;
          ctx.fill();
          if (m.life > 0.8) {
            const f = (m.life - 0.8) / 0.2;
            ctx.beginPath();
            ctx.arc(m.x, m.y, m.r * 6, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${c}, ${f * 0.3})`;
            ctx.fill();
          }
        }

        ctx.beginPath();
        ctx.arc(m.x, m.y, m.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${c}, ${alpha})`;
        ctx.fill();
      }

      rafRef.current = requestAnimationFrame(tick);
    }

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      running = false;
      cancelAnimationFrame(rafRef.current);
      observer.disconnect();
    };
  }, []);

  // Spawn event motes — amplified: even v=1 spawns MIN_EVENT_MOTES
  const lastBucketRef = useRef<string>("");
  useEffect(() => {
    if (!data.length) return;
    const last = data[data.length - 1];
    if (!last || last.v === 0) return;
    const fp = `${data.length}:${last.v}`;
    if (fp === lastBucketRef.current) return;
    lastBucketRef.current = fp;

    const { w, h } = sizeRef.current.w > 0 ? sizeRef.current : { w: 100, h: 20 };
    // Amplify: minimum burst even for 1 event, scales up but caps at 24
    const count = Math.min(Math.max(last.v * 6, MIN_EVENT_MOTES), 24);
    for (let i = 0; i < count; i++) {
      motesRef.current.push(spawnEvent(w, h));
    }
    flashRef.current = 1;
  }, [data]);

  return (
    <canvas
      ref={canvasRef}
      className="w-full block"
      style={{ height }}
    />
  );
}

// ---------------------------------------------------------------------------
// Display: EKG — SVG scrolling trace of actual metric values
// ---------------------------------------------------------------------------

const EKG_POINTS = 30; // how many data points visible in the trace

function PulseEkg({
  data,
  color,
  height = 16,
}: {
  data: { v: number }[];
  color: string;
  height?: number;
}) {
  // Take the last EKG_POINTS values, normalize to 0..1
  const points = data.slice(-EKG_POINTS);
  const max = Math.max(1, ...points.map((p) => p.v));
  const hasActivity = points.some((p) => p.v > 0);

  // Build SVG path
  const w = 200;
  const h = 24;
  const pad = 2;
  const usableH = h - pad * 2;

  let pathD: string;
  if (!hasActivity) {
    // Idle: flat line with gentle bumps (heartbeat)
    pathD =
      `M0,${h / 2} L${w * 0.25},${h / 2} ` +
      `L${w * 0.28},${h / 2 - 2} L${w * 0.30},${h / 2 + 1} L${w * 0.32},${h / 2} ` +
      `L${w * 0.75},${h / 2} ` +
      `L${w * 0.78},${h / 2 - 2} L${w * 0.80},${h / 2 + 1} L${w * 0.82},${h / 2} ` +
      `L${w},${h / 2}`;
  } else {
    const step = w / Math.max(points.length - 1, 1);
    pathD = points
      .map((p, i) => {
        const x = i * step;
        const y = pad + usableH - (p.v / max) * usableH;
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }

  return (
    <div className="w-full overflow-hidden" style={{ height }}>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        className="w-full h-full"
        style={!hasActivity ? { animation: "ekg-scroll 4s linear infinite", width: "200%" } : undefined}
      >
        <defs>
          <linearGradient id="ekg-fade-l" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={color} stopOpacity="0" />
            <stop offset="15%" stopColor={color} stopOpacity="1" />
          </linearGradient>
        </defs>
        <path
          d={pathD}
          stroke={hasActivity ? color : color}
          fill="none"
          strokeWidth={hasActivity ? "1.5" : "1"}
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={hasActivity ? 1 : 0.25}
        />
        {/* Glow dot at the leading edge when active */}
        {hasActivity && points.length > 0 && (() => {
          const lastP = points[points.length - 1];
          const x = w;
          const y = pad + usableH - (lastP.v / max) * usableH;
          return (
            <>
              <circle cx={x} cy={y} r="4" fill={color} opacity="0.3" />
              <circle cx={x} cy={y} r="1.5" fill={color} opacity="0.9" />
            </>
          );
        })()}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Display: Numeric — big counter with flash-on-change
// ---------------------------------------------------------------------------

function PulseNumeric({
  data,
  def,
  latest,
}: {
  data: { v: number }[];
  def: MetricDef;
  latest: MetricsBucket | null;
}) {
  const value = useMemo(() => {
    if (!latest) return 0;
    const catKey = CATEGORY_KEY_MAP[def.key];
    if (catKey) return latest.by_category?.[catKey] ?? 0;
    return latest[def.key as keyof MetricsBucket] as number;
  }, [latest, def.key]);

  // Running total across all buckets in the ring
  const total = useMemo(
    () => data.reduce((sum, d) => sum + d.v, 0),
    [data],
  );

  // Flash on value change
  const prevRef = useRef(value);
  const [changed, setChanged] = useState(false);
  useEffect(() => {
    if (value !== prevRef.current) {
      setChanged(true);
      const t = setTimeout(() => setChanged(false), 800);
      prevRef.current = value;
      return () => clearTimeout(t);
    }
  }, [value]);

  return (
    <div className="flex items-center justify-between h-4">
      <span
        className={`text-xs font-mono tabular-nums transition-all duration-300 ${
          changed
            ? "text-[var(--foreground)] font-bold scale-110"
            : value > 0
              ? "text-[var(--foreground)]"
              : "text-muted-foreground/50"
        }`}
        style={{ color: changed ? def.color : undefined }}
      >
        {def.format(value)}
      </span>
      <span className="text-[8px] text-muted-foreground/40 font-mono tabular-nums">
        Σ{total}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Collapsed mode — pulsing dot
// ---------------------------------------------------------------------------

function PulseDot({ hasErrors, hasActivity, connected }: { hasErrors: boolean; hasActivity: boolean; connected: boolean }) {
  const color = hasErrors
    ? "bg-[var(--pulse-errors)]"
    : hasActivity
      ? "bg-[var(--pulse-ops)]"
      : connected
        ? "bg-[var(--pulse-ops)]/30"
        : "bg-muted-foreground/40";

  const anim = hasActivity || hasErrors
    ? "animate-pulse"
    : connected
      ? "animate-pulse [animation-duration:3s]"
      : "";

  return (
    <div className="flex items-center justify-center h-8 w-full">
      <div className={`h-2 w-2 rounded-full ${color} ${anim}`} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Config popover
// ---------------------------------------------------------------------------

export type PulsePosition = "header" | "footer";

function PulseConfig({
  selected,
  onToggle,
  position,
  onPositionChange,
  displayMode,
  onDisplayModeChange,
}: {
  selected: MetricKey[];
  onToggle: (key: MetricKey) => void;
  position: PulsePosition;
  onPositionChange: (pos: PulsePosition) => void;
  displayMode: DisplayMode;
  onDisplayModeChange: (mode: DisplayMode) => void;
}) {
  const aggregateDefs = METRIC_DEFS.filter((d) => d.group === "aggregate");
  const categoryDefs = METRIC_DEFS.filter((d) => d.group === "category");

  const renderMetricCheckbox = (def: MetricDef) => {
    const isSelected = selected.includes(def.key);
    const disabled = !isSelected && selected.length >= MAX_SELECTED;
    return (
      <label
        key={def.key}
        className={`flex items-center gap-2 rounded px-2 py-1 text-sm cursor-pointer hover:bg-accent ${disabled ? "opacity-40 cursor-not-allowed" : ""}`}
      >
        <input
          type="checkbox"
          checked={isSelected}
          disabled={disabled}
          onChange={() => onToggle(def.key)}
          className="rounded border-border"
        />
        <span
          className="h-2 w-2 rounded-full shrink-0"
          style={{ backgroundColor: def.color }}
        />
        {def.label}
      </label>
    );
  };

  return (
    <div className="space-y-3 p-1">
      {/* Display mode */}
      <div>
        <div className="text-xs font-medium text-muted-foreground mb-1">Display</div>
        <div className="flex gap-1">
          {(["motes", "ekg", "numeric"] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => onDisplayModeChange(mode)}
              className={`flex-1 rounded px-2 py-1 text-xs ${
                displayMode === mode
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
            >
              {DISPLAY_MODE_LABELS[mode]}
            </button>
          ))}
        </div>
      </div>
      {/* Metrics */}
      <div className="border-t border-border pt-2">
        <div className="text-xs font-medium text-muted-foreground">Metrics (max 3)</div>
        <div className="space-y-1">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground/60 px-2 pt-1">Aggregate</div>
          {aggregateDefs.map(renderMetricCheckbox)}
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground/60 px-2 pt-2">By category</div>
          {categoryDefs.map(renderMetricCheckbox)}
        </div>
      </div>
      {/* Position */}
      <div className="border-t border-border pt-2">
        <div className="text-xs font-medium text-muted-foreground mb-1">Position</div>
        <div className="flex gap-1">
          {(["header", "footer"] as const).map((pos) => (
            <button
              key={pos}
              onClick={() => onPositionChange(pos)}
              className={`flex-1 rounded px-2 py-1 text-xs capitalize ${
                position === pos
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
            >
              {pos}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function SystemPulse() {
  const { buckets, latest, connected } = useMetricsStream();
  const { state: sidebarState } = useSidebar();
  const collapsed = sidebarState === "collapsed";

  const [selected, setSelected] = useState<MetricKey[]>(DEFAULT_METRICS);
  const [displayMode, setDisplayMode] = useState<DisplayMode>(DEFAULT_DISPLAY);

  useEffect(() => {
    setSelected(loadSelectedMetrics());
    setDisplayMode(loadDisplayMode());
  }, []);

  const toggleMetric = useCallback((key: MetricKey) => {
    setSelected((prev) => {
      const next = prev.includes(key)
        ? prev.filter((k) => k !== key)
        : prev.length < MAX_SELECTED
          ? [...prev, key]
          : prev;
      if (next.length === 0) return prev;
      localStorage.setItem(LS_METRICS_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const handleDisplayModeChange = useCallback((mode: DisplayMode) => {
    setDisplayMode(mode);
    localStorage.setItem(LS_DISPLAY_KEY, mode);
  }, []);

  const [position, setPosition] = useState<PulsePosition>("header");
  useEffect(() => {
    const stored = localStorage.getItem(LS_POSITION_KEY);
    if (stored === "header" || stored === "footer") setPosition(stored);
  }, []);

  const handlePositionChange = useCallback((pos: PulsePosition) => {
    setPosition(pos);
    localStorage.setItem(LS_POSITION_KEY, pos);
    window.dispatchEvent(new CustomEvent("cairn:ekg-position-change", { detail: pos }));
  }, []);

  const selectedDefs = useMemo(
    () => selected.map((k) => METRIC_MAP.get(k)!).filter(Boolean),
    [selected],
  );

  const hasErrors = (latest?.errors ?? 0) > 0;
  const hasActivity = (latest?.ops_count ?? 0) > 0;

  // Track previous ops_count to detect activity transitions
  const prevOpsRef = useRef(0);
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    const ops = latest?.ops_count ?? 0;
    if (ops > 0 && ops !== prevOpsRef.current) {
      setFlash(true);
      const t = setTimeout(() => setFlash(false), 2000);
      prevOpsRef.current = ops;
      return () => clearTimeout(t);
    }
    prevOpsRef.current = ops;
  }, [latest?.ops_count]);

  const configPopover = (
    <PulseConfig
      selected={selected}
      onToggle={toggleMetric}
      position={position}
      onPositionChange={handlePositionChange}
      displayMode={displayMode}
      onDisplayModeChange={handleDisplayModeChange}
    />
  );

  if (collapsed) {
    return (
      <Popover>
        <PopoverTrigger asChild>
          <button className="w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md" aria-label="System pulse">
            <PulseDot hasErrors={hasErrors} hasActivity={hasActivity} connected={connected} />
          </button>
        </PopoverTrigger>
        <PopoverContent side="right" align="start" className="w-56">
          {configPopover}
        </PopoverContent>
      </Popover>
    );
  }

  // Render the per-metric visualization based on display mode
  function renderMetricLane(def: MetricDef) {
    const series = extractSeries(buckets, def.key);

    if (displayMode === "numeric") {
      return (
        <div key={def.key} className="flex items-center gap-1.5">
          <span className="text-[8px] text-muted-foreground/60 w-5 shrink-0">
            {def.shortLabel}
          </span>
          <div className="flex-1 min-w-0">
            <PulseNumeric data={series} def={def} latest={latest} />
          </div>
        </div>
      );
    }

    if (displayMode === "ekg") {
      const value = latest
        ? CATEGORY_KEY_MAP[def.key]
          ? (latest.by_category?.[CATEGORY_KEY_MAP[def.key]] ?? 0)
          : (latest[def.key as keyof MetricsBucket] as number)
        : 0;
      return (
        <div key={def.key} className="flex items-center gap-1.5">
          <span
            className={`text-[9px] w-6 text-right tabular-nums shrink-0 transition-colors duration-300 ${
              flash && def.key === "ops_count"
                ? "text-[var(--pulse-ops)] font-bold"
                : "text-muted-foreground"
            }`}
          >
            {latest ? def.format(value) : "--"}
          </span>
          <div className="flex-1 min-w-0">
            <PulseEkg data={series} color={def.color} height={16} />
          </div>
          <span className="text-[8px] text-muted-foreground/60 w-5 shrink-0">
            {def.shortLabel}
          </span>
        </div>
      );
    }

    // Default: motes
    const value = latest
      ? CATEGORY_KEY_MAP[def.key]
        ? (latest.by_category?.[CATEGORY_KEY_MAP[def.key]] ?? 0)
        : (latest[def.key as keyof MetricsBucket] as number)
      : 0;
    return (
      <div key={def.key} className="flex items-center gap-1.5">
        <span
          className={`text-[9px] w-6 text-right tabular-nums shrink-0 transition-colors duration-300 ${
            flash && def.key === "ops_count"
              ? "text-[var(--pulse-ops)] font-bold"
              : "text-muted-foreground"
          }`}
        >
          {latest ? def.format(value) : "--"}
        </span>
        <div className="flex-1 min-w-0">
          <PulseMotes
            data={series}
            color={def.color}
            height={16}
          />
        </div>
        <span className="text-[8px] text-muted-foreground/60 w-5 shrink-0">
          {def.shortLabel}
        </span>
      </div>
    );
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          className={`w-full rounded-md px-2 py-1.5 hover:bg-sidebar-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group ${flash ? "bg-[var(--pulse-ops)]/10" : ""}`}
          style={{ transition: "background-color 0.3s ease-out" }}
          aria-label="System pulse — click to configure"
        >
          <div className="flex items-center justify-between mb-0.5">
            <div className="flex items-center gap-1.5">
              <div
                className={`rounded-full shrink-0 transition-all duration-300 ${
                  connected
                    ? hasErrors
                      ? "h-1.5 w-1.5 bg-[var(--pulse-errors)] animate-pulse"
                      : flash
                        ? "h-2.5 w-2.5 bg-[var(--pulse-ops)] shadow-[0_0_6px_var(--pulse-ops)]"
                        : "h-1.5 w-1.5 bg-[var(--pulse-ops)]"
                    : "h-1.5 w-1.5 bg-muted-foreground/40"
                }`}
              />
              <span className="text-[10px] text-muted-foreground">
                {connected ? "live" : "disconnected"}
              </span>
            </div>
            <Settings2 className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
          <div className="space-y-0.5">
            {selectedDefs.map(renderMetricLane)}
          </div>
        </button>
      </PopoverTrigger>
      <PopoverContent side="right" align="start" className="w-56">
        {configPopover}
      </PopoverContent>
    </Popover>
  );
}

/** Export position helpers for SidebarNav to consume */
export { LS_POSITION_KEY };
export type { PulsePosition as SystemPulsePosition };
