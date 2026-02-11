import { useState, useEffect, useCallback, useRef } from "react";

// ═══════════════════════════════════════════════════════════════════
// CONFIG
// ═══════════════════════════════════════════════════════════════════
const API = "https://basis-deploy-guide.replit.app";

// ═══════════════════════════════════════════════════════════════════
// DESIGN TOKENS
// ═══════════════════════════════════════════════════════════════════
const T = {
  bg: "#06080d",
  bgCard: "#0a0d14",
  bgHover: "#0d1019",
  bgElevated: "#0f1320",
  border: "#151a27",
  borderLight: "#1c2236",
  text: "#c8cdd8",
  textMuted: "#6b7280",
  textDim: "#3d4555",
  textBright: "#e8ecf4",
  accent: "#22d3a7",
  accentDim: "#22d3a733",
  accentGlow: "#22d3a715",
  blue: "#3b82f6",
  blueDim: "#3b82f633",
  amber: "#f59e0b",
  amberDim: "#f59e0b33",
  red: "#ef4444",
  redDim: "#ef444433",
  mono: "'IBM Plex Mono', 'Fira Code', monospace",
  sans: "'Instrument Sans', 'DM Sans', system-ui, sans-serif",
  display: "'Newsreader', 'Playfair Display', Georgia, serif",
};

const gradeColor = (g) => {
  if (!g) return T.textDim;
  const c = g[0];
  return c === "A" ? T.accent : c === "B" ? T.amber : c === "C" ? "#f97316" : T.red;
};

const scoreColor = (s) => {
  if (s == null) return T.textDim;
  if (s >= 85) return T.accent;
  if (s >= 70) return T.amber;
  if (s >= 55) return "#f97316";
  return T.red;
};

const fmt = (n, d = 1) => (n != null ? Number(n).toFixed(d) : "—");
const fmtB = (n) => {
  if (!n) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toLocaleString()}`;
};

// ═══════════════════════════════════════════════════════════════════
// API HOOKS
// ═══════════════════════════════════════════════════════════════════
function useScores() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [ts, setTs] = useState(null);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const r = await fetch(`${API}/api/scores`);
        const d = await r.json();
        if (mounted) {
          setData(d.stablecoins || []);
          setTs(d.timestamp);
          setLoading(false);
        }
      } catch (e) {
        if (mounted) { setError(e.message); setLoading(false); }
      }
    };
    load();
    const interval = setInterval(load, 300000); // refresh every 5 min
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  return { data, loading, error, ts };
}

function useCoinDetail(coinId) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!coinId) return;
    setLoading(true);
    fetch(`${API}/api/scores/${coinId}`)
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [coinId]);

  return { data, loading };
}

function useCoinHistory(coinId, days = 90) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!coinId) return;
    setLoading(true);
    fetch(`${API}/api/scores/${coinId}/history?days=${days}`)
      .then((r) => r.json())
      .then((d) => { setData(d.history || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [coinId, days]);

  return { data, loading };
}

// ═══════════════════════════════════════════════════════════════════
// PRIMITIVES
// ═══════════════════════════════════════════════════════════════════

function GradePill({ grade }) {
  const c = gradeColor(grade);
  return (
    <span
      style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        padding: "2px 8px", borderRadius: 3,
        background: `${c}18`, border: `1px solid ${c}30`,
        color: c, fontSize: 11, fontWeight: 600,
        fontFamily: T.mono, letterSpacing: 0.5, lineHeight: "18px",
      }}
    >
      {grade}
    </span>
  );
}

function ScoreNum({ value, size = "md" }) {
  const c = scoreColor(value);
  const fs = size === "lg" ? 28 : size === "sm" ? 13 : 16;
  return (
    <span
      style={{
        color: c, fontSize: fs, fontWeight: 700,
        fontFamily: T.mono, letterSpacing: -0.5,
      }}
    >
      {fmt(value, 1)}
    </span>
  );
}

function CategoryBar({ label, score, weight, color }) {
  const c = color || scoreColor(score);
  const pct = score != null ? Math.min(100, score) : 0;
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 11, color: T.textMuted, fontFamily: T.sans }}>
          {label}
          {weight != null && (
            <span style={{ color: T.textDim, fontSize: 10, marginLeft: 4 }}>
              {(weight * 100).toFixed(0)}%
            </span>
          )}
        </span>
        <span style={{ fontSize: 12, fontFamily: T.mono, fontWeight: 600, color: c }}>
          {score != null ? fmt(score, 1) : "—"}
        </span>
      </div>
      <div style={{ height: 4, borderRadius: 2, background: T.border }}>
        <div
          style={{
            height: "100%", borderRadius: 2, width: `${pct}%`,
            background: c, opacity: 0.8,
            transition: "width 0.8s cubic-bezier(0.22, 1, 0.36, 1)",
          }}
        />
      </div>
    </div>
  );
}

function Sparkline({ data, width = 120, height = 36 }) {
  if (!data || data.length < 2) return <div style={{ width, height, background: T.border, borderRadius: 3, opacity: 0.3 }} />;
  const scores = data.map((d) => (typeof d === "number" ? d : d.score)).filter((s) => s != null);
  if (scores.length < 2) return null;
  const min = Math.min(...scores) - 1;
  const max = Math.max(...scores) + 1;
  const range = max - min || 1;
  const pts = scores.map((v, i) =>
    `${(i / (scores.length - 1)) * width},${height - ((v - min) / range) * (height - 4) - 2}`
  ).join(" ");
  const trending = scores[scores.length - 1] >= scores[0];
  const c = trending ? T.accent : T.red;
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <polyline points={pts} fill="none" stroke={c} strokeWidth="1.5" strokeLinejoin="round" opacity="0.7" />
    </svg>
  );
}

function ScoreChart({ history, width = 700, height = 200 }) {
  if (!history || history.length < 1) {
    return (
      <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: T.textDim, fontSize: 12, fontFamily: T.sans }}>
        Accumulating history data...
      </div>
    );
  }

  const scores = history.map((h) => h.score).filter((s) => s != null);
  if (scores.length < 1) return null;

  const min = Math.min(...scores) - 2;
  const max = Math.max(...scores) + 2;
  const range = max - min || 1;

  const pts = scores.map((v, i) =>
    `${(i / Math.max(scores.length - 1, 1)) * width},${height - ((v - min) / range) * (height - 24) - 12}`
  ).join(" ");

  const areaPath = pts + ` ${width},${height} 0,${height}`;

  // Y-axis labels
  const ySteps = [min, min + range * 0.25, min + range * 0.5, min + range * 0.75, max];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: height }}>
      <defs>
        <linearGradient id="chartArea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={T.accent} stopOpacity="0.12" />
          <stop offset="100%" stopColor={T.accent} stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* Grid lines */}
      {ySteps.map((v, i) => {
        const y = height - ((v - min) / range) * (height - 24) - 12;
        return (
          <g key={i}>
            <line x1={32} y1={y} x2={width} y2={y} stroke={T.border} strokeWidth="0.5" />
            <text x={28} y={y + 3} fill={T.textDim} fontSize="9" fontFamily={T.mono} textAnchor="end">
              {v.toFixed(0)}
            </text>
          </g>
        );
      })}
      <polygon points={areaPath} fill="url(#chartArea)" />
      <polyline points={pts} fill="none" stroke={T.accent} strokeWidth="1.5" strokeLinejoin="round" />
      {/* Endpoints */}
      {scores.length > 0 && (
        <circle
          cx={(scores.length - 1) / Math.max(scores.length - 1, 1) * width}
          cy={height - ((scores[scores.length - 1] - min) / range) * (height - 24) - 12}
          r="3" fill={T.accent}
        />
      )}
      {/* Date labels */}
      {history.length > 1 && (
        <>
          <text x={32} y={height - 1} fill={T.textDim} fontSize="9" fontFamily={T.mono}>
            {history[0].date}
          </text>
          <text x={width} y={height - 1} fill={T.textDim} fontSize="9" fontFamily={T.mono} textAnchor="end">
            {history[history.length - 1].date}
          </text>
        </>
      )}
    </svg>
  );
}

// ═══════════════════════════════════════════════════════════════════
// HEADER
// ═══════════════════════════════════════════════════════════════════

function Header({ view, setView, ts }) {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60000);
    return () => clearInterval(t);
  }, []);

  const tabs = [
    { id: "rankings", label: "Rankings" },
    { id: "methodology", label: "Methodology" },
  ];

  return (
    <header
      style={{
        position: "sticky", top: 0, zIndex: 100,
        borderBottom: `1px solid ${T.border}`,
        background: `${T.bg}ee`, backdropFilter: "blur(12px)",
        padding: "0 24px", height: 52,
        display: "flex", alignItems: "center", gap: 24,
      }}
    >
      {/* Logo */}
      <div
        style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", flexShrink: 0 }}
        onClick={() => setView("rankings")}
      >
        <div
          style={{
            width: 26, height: 26, borderRadius: 5,
            background: `linear-gradient(135deg, ${T.accent}, ${T.blue})`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 10, fontWeight: 800, color: "#000", letterSpacing: 2,
          }}
        >
          B
        </div>
        <span style={{ fontSize: 14, fontWeight: 700, color: T.textBright, letterSpacing: 3, fontFamily: T.sans }}>
          BASIS
        </span>
      </div>

      {/* Separator */}
      <div style={{ width: 1, height: 24, background: T.border }} />

      {/* Tabs */}
      <nav style={{ display: "flex", gap: 2 }}>
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setView(t.id)}
            style={{
              padding: "6px 14px", borderRadius: 4, border: "none", cursor: "pointer",
              fontSize: 12, fontWeight: view === t.id ? 600 : 400,
              fontFamily: T.sans, letterSpacing: 0.3,
              color: view === t.id ? T.textBright : T.textMuted,
              background: view === t.id ? T.bgElevated : "transparent",
              transition: "all 0.15s",
            }}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {/* Right side */}
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 16 }}>
        <span style={{ fontSize: 10, color: T.textDim, fontFamily: T.mono }}>
          SII v1.0.0
        </span>
        {ts && (
          <span style={{ fontSize: 10, color: T.textDim, fontFamily: T.mono }}>
            Updated {new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>
        )}
        <div
          style={{
            width: 6, height: 6, borderRadius: "50%",
            background: T.accent, boxShadow: `0 0 6px ${T.accent}`,
          }}
        />
      </div>
    </header>
  );
}

// ═══════════════════════════════════════════════════════════════════
// RANKINGS VIEW
// ═══════════════════════════════════════════════════════════════════

function RankingsView({ scores, loading, onSelect }) {
  if (loading) {
    return (
      <div style={{ padding: 40, display: "flex", justifyContent: "center" }}>
        <div style={{ color: T.textDim, fontFamily: T.mono, fontSize: 12 }}>Loading scores...</div>
      </div>
    );
  }

  if (!scores || scores.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: T.textDim, fontSize: 13 }}>
        No scores available. Waiting for first scoring cycle.
      </div>
    );
  }

  const sorted = [...scores].sort((a, b) => (b.score || 0) - (a.score || 0));

  return (
    <div style={{ padding: "24px 24px 64px", maxWidth: 1100, margin: "0 auto" }}>
      {/* Title */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{
          margin: 0, fontSize: 22, fontWeight: 600, color: T.textBright,
          fontFamily: T.display, letterSpacing: -0.3,
        }}>
          Stablecoin Integrity Index
        </h1>
        <p style={{ margin: "6px 0 0", fontSize: 12, color: T.textMuted, fontFamily: T.sans, lineHeight: 1.5 }}>
          Standardized risk surfaces for {sorted.length} stablecoins · Updated hourly · Deterministic methodology
        </p>
      </div>

      {/* Table */}
      <div style={{ borderRadius: 8, border: `1px solid ${T.border}`, overflow: "hidden" }}>
        {/* Header */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "36px 1.5fr 72px 48px 88px 96px 96px 64px 64px 64px 64px 64px",
            padding: "10px 16px",
            background: T.bgCard,
            borderBottom: `1px solid ${T.border}`,
            fontSize: 9, fontWeight: 600, color: T.textDim,
            textTransform: "uppercase", letterSpacing: 1.5,
            fontFamily: T.mono,
          }}
        >
          <span>#</span>
          <span>Stablecoin</span>
          <span style={{ textAlign: "right" }}>SII</span>
          <span style={{ textAlign: "center" }}>Grade</span>
          <span style={{ textAlign: "right" }}>Price</span>
          <span style={{ textAlign: "right" }}>Mkt Cap</span>
          <span style={{ textAlign: "right" }}>Vol 24h</span>
          <span style={{ textAlign: "right" }}>Peg</span>
          <span style={{ textAlign: "right" }}>Liq</span>
          <span style={{ textAlign: "right" }}>Flow</span>
          <span style={{ textAlign: "right" }}>Dist</span>
          <span style={{ textAlign: "right" }}>Str</span>
        </div>

        {/* Rows */}
        {sorted.map((coin, i) => {
          const cats = coin.categories || {};
          const pegScore = typeof cats.peg === "object" ? cats.peg?.score : cats.peg;
          const liqScore = typeof cats.liquidity === "object" ? cats.liquidity?.score : cats.liquidity;
          const flowScore = typeof cats.flows === "object" ? cats.flows?.score : cats.flows;
          const distScore = typeof cats.distribution === "object" ? cats.distribution?.score : cats.distribution;
          const strScore = typeof cats.structural === "object" ? cats.structural?.score : cats.structural;

          return (
            <div
              key={coin.id}
              onClick={() => onSelect(coin.id)}
              style={{
                display: "grid",
                gridTemplateColumns: "36px 1.5fr 72px 48px 88px 96px 96px 64px 64px 64px 64px 64px",
                padding: "12px 16px",
                cursor: "pointer",
                alignItems: "center",
                borderBottom: `1px solid ${T.bg}`,
                transition: "background 0.1s",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = T.bgHover)}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              <span style={{ color: T.textDim, fontSize: 11, fontFamily: T.mono }}>{i + 1}</span>

              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div
                  style={{
                    width: 28, height: 28, borderRadius: "50%",
                    background: `${scoreColor(coin.score)}10`,
                    border: `1px solid ${scoreColor(coin.score)}25`,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 9, fontWeight: 700, color: scoreColor(coin.score),
                    fontFamily: T.mono,
                  }}
                >
                  {coin.symbol?.slice(0, 2)}
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13, color: T.textBright, fontFamily: T.sans }}>
                    {coin.symbol}
                  </div>
                  <div style={{ fontSize: 10, color: T.textDim }}>{coin.issuer}</div>
                </div>
              </div>

              <div style={{ textAlign: "right" }}>
                <ScoreNum value={coin.score} />
              </div>

              <div style={{ textAlign: "center" }}>
                <GradePill grade={coin.grade} />
              </div>

              <span style={{ textAlign: "right", fontSize: 12, color: T.text, fontFamily: T.mono }}>
                ${coin.price?.toFixed(4)}
              </span>

              <span style={{ textAlign: "right", fontSize: 12, color: T.textMuted, fontFamily: T.mono }}>
                {fmtB(coin.market_cap)}
              </span>

              <span style={{ textAlign: "right", fontSize: 12, color: T.textMuted, fontFamily: T.mono }}>
                {fmtB(coin.volume_24h)}
              </span>

              {[pegScore, liqScore, flowScore, distScore, strScore].map((s, j) => (
                <span
                  key={j}
                  style={{
                    textAlign: "right", fontSize: 11,
                    fontFamily: T.mono, fontWeight: 500,
                    color: s != null ? scoreColor(s) : T.textDim,
                    opacity: s != null ? 0.85 : 0.4,
                  }}
                >
                  {s != null ? fmt(s, 0) : "—"}
                </span>
              ))}
            </div>
          );
        })}
      </div>

      {/* Footer note */}
      <div style={{ marginTop: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 10, color: T.textDim, fontFamily: T.mono }}>
          SII = 0.30×Peg + 0.25×Liq + 0.15×Flow + 0.10×Dist + 0.20×Struct
        </span>
        <span style={{ fontSize: 10, color: T.textDim, fontFamily: T.mono }}>
          {sorted[0]?.component_count || "—"} components · {sorted.length} stablecoins
        </span>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// DETAIL VIEW
// ═══════════════════════════════════════════════════════════════════

function DetailView({ coinId, onBack }) {
  const { data: coin, loading: detailLoading } = useCoinDetail(coinId);
  const { data: history, loading: histLoading } = useCoinHistory(coinId, 90);

  if (detailLoading || !coin) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: T.textDim, fontFamily: T.mono, fontSize: 12 }}>
        Loading {coinId}...
      </div>
    );
  }

  const cats = coin.categories || {};
  const strBk = coin.structural_breakdown || {};

  // Normalize category access (handle both {score, weight} and flat number)
  const getCat = (obj) => {
    if (obj == null) return { score: null, weight: null };
    if (typeof obj === "object") return obj;
    return { score: obj, weight: null };
  };

  const peg = getCat(cats.peg);
  const liq = getCat(cats.liquidity);
  const flow = getCat(cats.flows);
  const dist = getCat(cats.distribution);
  const str = getCat(cats.structural);

  const reserves = getCat(strBk.reserves);
  const contract = getCat(strBk.contract);
  const oracle = getCat(strBk.oracle);
  const governance = getCat(strBk.governance);
  const network = getCat(strBk.network);

  return (
    <div style={{ padding: "24px 24px 64px", maxWidth: 1100, margin: "0 auto" }}>
      {/* Back */}
      <button
        onClick={onBack}
        style={{
          background: "none", border: "none", color: T.textMuted,
          cursor: "pointer", fontSize: 12, fontFamily: T.sans,
          padding: 0, marginBottom: 20,
        }}
      >
        ← Back to Rankings
      </button>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 20, marginBottom: 32 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <h1 style={{
              margin: 0, fontSize: 26, fontWeight: 600, color: T.textBright,
              fontFamily: T.display, letterSpacing: -0.5,
            }}>
              {coin.name}
            </h1>
            <span style={{ fontSize: 14, color: T.textDim, fontFamily: T.mono }}>{coin.symbol}</span>
            <GradePill grade={coin.grade} />
          </div>
          <div style={{ fontSize: 12, color: T.textMuted, marginTop: 6, fontFamily: T.sans }}>
            Issued by {coin.issuer} · {coin.component_count || "—"} components measured
          </div>
        </div>

        <div style={{ textAlign: "right" }}>
          <ScoreNum value={coin.score} size="lg" />
          <div style={{ fontSize: 11, color: T.textDim, fontFamily: T.mono, marginTop: 4 }}>
            ${coin.price?.toFixed(4)} · MCap {fmtB(coin.market_cap)}
          </div>
        </div>
      </div>

      {/* Chart */}
      <div
        style={{
          borderRadius: 8, border: `1px solid ${T.border}`,
          padding: "16px 20px 12px", marginBottom: 20, background: T.bgCard,
        }}
      >
        <div style={{
          fontSize: 10, fontWeight: 600, color: T.textDim,
          textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 12,
          fontFamily: T.mono,
        }}>
          Score History
        </div>
        <ScoreChart history={history} />
      </div>

      {/* Category + Structural Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
        {/* Categories */}
        <div
          style={{
            borderRadius: 8, border: `1px solid ${T.border}`,
            padding: "16px 20px", background: T.bgCard,
          }}
        >
          <div style={{
            fontSize: 10, fontWeight: 600, color: T.textDim,
            textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 16,
            fontFamily: T.mono,
          }}>
            Category Scores
          </div>
          <CategoryBar label="Peg Stability" score={peg.score} weight={peg.weight || 0.30} />
          <CategoryBar label="Liquidity Depth" score={liq.score} weight={liq.weight || 0.25} />
          <CategoryBar label="Mint/Burn Flows" score={flow.score} weight={flow.weight || 0.15} />
          <CategoryBar label="Holder Distribution" score={dist.score} weight={dist.weight || 0.10} />
          <CategoryBar label="Structural Risk" score={str.score} weight={str.weight || 0.20} />
        </div>

        {/* Structural */}
        <div
          style={{
            borderRadius: 8, border: `1px solid ${T.border}`,
            padding: "16px 20px", background: T.bgCard,
          }}
        >
          <div style={{
            fontSize: 10, fontWeight: 600, color: T.textDim,
            textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 16,
            fontFamily: T.mono,
          }}>
            Structural Breakdown
          </div>
          <CategoryBar label="Reserves & Collateral" score={reserves.score} weight={reserves.weight || 0.30} color={T.blue} />
          <CategoryBar label="Smart Contract" score={contract.score} weight={contract.weight || 0.20} color={T.blue} />
          <CategoryBar label="Oracle Integrity" score={oracle.score} weight={oracle.weight || 0.15} color={T.blue} />
          <CategoryBar label="Governance & Ops" score={governance.score} weight={governance.weight || 0.20} color={T.blue} />
          <CategoryBar label="Network & Chain" score={network.score} weight={network.weight || 0.15} color={T.blue} />
        </div>
      </div>

      {/* Components Table */}
      {coin.components && coin.components.length > 0 && (
        <div
          style={{
            borderRadius: 8, border: `1px solid ${T.border}`,
            padding: "16px 20px", background: T.bgCard,
          }}
        >
          <div style={{
            fontSize: 10, fontWeight: 600, color: T.textDim,
            textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 12,
            fontFamily: T.mono,
          }}>
            Component Readings · {coin.components.length} active
          </div>

          <div style={{ maxHeight: 400, overflowY: "auto" }}>
            {/* Group by category */}
            {Object.entries(
              coin.components.reduce((acc, c) => {
                const cat = c.category || "other";
                if (!acc[cat]) acc[cat] = [];
                acc[cat].push(c);
                return acc;
              }, {})
            )
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([category, components]) => (
                <div key={category} style={{ marginBottom: 16 }}>
                  <div style={{
                    fontSize: 10, fontWeight: 600, color: T.accent,
                    textTransform: "uppercase", letterSpacing: 1,
                    marginBottom: 6, fontFamily: T.mono, opacity: 0.7,
                  }}>
                    {category.replace(/_/g, " ")}
                  </div>
                  {components.sort((a, b) => (b.normalized_score || 0) - (a.normalized_score || 0)).map((comp) => (
                    <div
                      key={comp.id}
                      style={{
                        display: "flex", justifyContent: "space-between",
                        padding: "4px 0", borderBottom: `1px solid ${T.bg}`,
                        fontSize: 11,
                      }}
                    >
                      <span style={{ color: T.textMuted, fontFamily: T.sans }}>
                        {(comp.id || "").replace(/_/g, " ")}
                      </span>
                      <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
                        <span style={{ color: T.textDim, fontFamily: T.mono, fontSize: 10 }}>
                          {comp.raw_value != null ? (typeof comp.raw_value === "number" ? comp.raw_value.toFixed(4) : comp.raw_value) : "—"}
                        </span>
                        <span style={{
                          color: scoreColor(comp.normalized_score),
                          fontFamily: T.mono, fontWeight: 600, minWidth: 36, textAlign: "right",
                        }}>
                          {fmt(comp.normalized_score, 1)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// METHODOLOGY VIEW
// ═══════════════════════════════════════════════════════════════════

function MethodologyView() {
  return (
    <div style={{ padding: "24px 24px 64px", maxWidth: 780, margin: "0 auto" }}>
      <h1 style={{
        margin: "0 0 8px", fontSize: 22, fontWeight: 600, color: T.textBright,
        fontFamily: T.display, letterSpacing: -0.3,
      }}>
        Methodology
      </h1>
      <p style={{ margin: "0 0 28px", fontSize: 12, color: T.textMuted, fontFamily: T.sans }}>
        SII v1.0.0 — Deterministic, versioned, reproducible
      </p>

      {/* What is SII */}
      <section style={{ marginBottom: 28 }}>
        <div style={{
          borderRadius: 8, border: `1px solid ${T.border}`,
          padding: "20px 24px", background: T.bgCard,
        }}>
          <h2 style={{
            margin: "0 0 12px", fontSize: 14, fontWeight: 600, color: T.textBright,
            fontFamily: T.sans,
          }}>
            What is the Stablecoin Integrity Index?
          </h2>
          <p style={{ margin: 0, fontSize: 13, color: T.text, fontFamily: T.sans, lineHeight: 1.7 }}>
            SII is a standardized risk surface that normalizes fragmented data about stablecoin health
            into a single comparable score. It measures peg stability, liquidity depth, mint/burn dynamics,
            holder distribution, and structural risk across multiple data sources. The methodology is
            deterministic — the same inputs always produce the same outputs — and version-controlled
            so changes are announced in advance and retroactively reproducible.
          </p>
        </div>
      </section>

      {/* Formula */}
      <section style={{ marginBottom: 28 }}>
        <div style={{
          borderRadius: 8, border: `1px solid ${T.border}`,
          padding: "20px 24px", background: T.bgCard,
        }}>
          <div style={{
            fontSize: 10, fontWeight: 600, color: T.accent,
            textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 14,
            fontFamily: T.mono,
          }}>
            Formula
          </div>
          <div style={{
            fontFamily: T.mono, fontSize: 14, color: T.textBright, lineHeight: 2.2,
            padding: "8px 0",
          }}>
            SII = <span style={{ color: T.accent }}>0.30</span>×Peg + <span style={{ color: T.accent }}>0.25</span>×Liquidity + <span style={{ color: T.accent }}>0.15</span>×Flows + <span style={{ color: T.accent }}>0.10</span>×Distribution + <span style={{ color: T.accent }}>0.20</span>×Structural
          </div>
          <div style={{
            fontFamily: T.mono, fontSize: 12, color: T.textMuted, lineHeight: 2.2,
            borderTop: `1px solid ${T.border}`, paddingTop: 8, marginTop: 4,
          }}>
            Structural = <span style={{ color: T.blue }}>0.30</span>×Reserves + <span style={{ color: T.blue }}>0.20</span>×Contract + <span style={{ color: T.blue }}>0.15</span>×Oracle + <span style={{ color: T.blue }}>0.20</span>×Governance + <span style={{ color: T.blue }}>0.15</span>×Network
          </div>
        </div>
      </section>

      {/* Categories */}
      <section style={{ marginBottom: 28 }}>
        <div style={{
          borderRadius: 8, border: `1px solid ${T.border}`,
          padding: "20px 24px", background: T.bgCard,
        }}>
          <div style={{
            fontSize: 10, fontWeight: 600, color: T.textDim,
            textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 16,
            fontFamily: T.mono,
          }}>
            Categories
          </div>
          {[
            { name: "Peg Stability", weight: 30, desc: "Current deviation, 24h max, 7d volatility, price floor/ceiling, cross-exchange variance, DEX/CEX spread, arbitrage efficiency", components: 10 },
            { name: "Liquidity Depth", weight: 25, desc: "Market cap, volume ratios, DEX pool depth, Curve 3pool balance, cross-chain liquidity, lending protocol TVL, exchange listing breadth", components: 12 },
            { name: "Mint/Burn Flows", weight: 15, desc: "Supply changes, turnover ratio, market cap stability, volume consistency, trading pair diversity", components: 9 },
            { name: "Holder Distribution", weight: 10, desc: "Top 10 wallet concentration, unique holder count, exchange address concentration", components: 3 },
            { name: "Structural Risk", weight: 20, desc: "Reserve quality, smart contract audits, oracle integrity, governance model, network deployment, regulatory compliance", components: 16 },
          ].map((cat, i) => (
            <div
              key={i}
              style={{
                display: "flex", gap: 16, padding: "14px 0",
                borderBottom: i < 4 ? `1px solid ${T.border}` : "none",
              }}
            >
              <div style={{
                minWidth: 44, textAlign: "right",
                fontFamily: T.mono, fontWeight: 700, fontSize: 18, color: T.accent,
              }}>
                {cat.weight}%
              </div>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13, color: T.textBright, fontFamily: T.sans }}>
                  {cat.name}
                </div>
                <div style={{ fontSize: 12, color: T.textMuted, marginTop: 3, lineHeight: 1.5, fontFamily: T.sans }}>
                  {cat.desc}
                </div>
                <div style={{ fontSize: 10, color: T.textDim, marginTop: 3, fontFamily: T.mono }}>
                  {cat.components} components
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Grade Scale */}
      <section style={{ marginBottom: 28 }}>
        <div style={{
          borderRadius: 8, border: `1px solid ${T.border}`,
          padding: "20px 24px", background: T.bgCard,
        }}>
          <div style={{
            fontSize: 10, fontWeight: 600, color: T.textDim,
            textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 14,
            fontFamily: T.mono,
          }}>
            Grade Scale
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 6 }}>
            {[
              { grade: "A+", range: "90–100" }, { grade: "A", range: "85–90" }, { grade: "A-", range: "80–85" },
              { grade: "B+", range: "75–80" }, { grade: "B", range: "70–75" }, { grade: "B-", range: "65–70" },
              { grade: "C+", range: "60–65" }, { grade: "C", range: "55–60" }, { grade: "C-", range: "50–55" },
              { grade: "D", range: "45–50" }, { grade: "F", range: "<45" },
            ].map((g) => (
              <div
                key={g.grade}
                style={{
                  padding: "8px 6px", borderRadius: 4, textAlign: "center",
                  background: `${gradeColor(g.grade)}08`,
                  border: `1px solid ${gradeColor(g.grade)}18`,
                }}
              >
                <div style={{
                  fontWeight: 700, fontSize: 14, color: gradeColor(g.grade),
                  fontFamily: T.mono,
                }}>
                  {g.grade}
                </div>
                <div style={{ fontSize: 9, color: T.textDim, marginTop: 2, fontFamily: T.mono }}>
                  {g.range}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Data Sources */}
      <section style={{ marginBottom: 28 }}>
        <div style={{
          borderRadius: 8, border: `1px solid ${T.border}`,
          padding: "20px 24px", background: T.bgCard,
        }}>
          <div style={{
            fontSize: 10, fontWeight: 600, color: T.textDim,
            textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 12,
            fontFamily: T.mono,
          }}>
            Data Sources
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
            {["CoinGecko Pro", "DeFiLlama", "Etherscan", "Curve Finance", "Issuer Attestations", "On-Chain Analysis"].map((s) => (
              <span
                key={s}
                style={{
                  padding: "4px 10px", borderRadius: 3,
                  background: T.bgElevated, color: T.textMuted,
                  fontSize: 11, fontFamily: T.sans,
                  border: `1px solid ${T.border}`,
                }}
              >
                {s}
              </span>
            ))}
          </div>
          <p style={{ margin: 0, fontSize: 12, color: T.textMuted, fontFamily: T.sans, lineHeight: 1.6 }}>
            102 components defined across 11 categories. 50 currently automated via live APIs.
            Scores update hourly. Deterministic formula — same inputs always produce same outputs.
            Version-controlled methodology with advance notice before changes.
          </p>
        </div>
      </section>

      {/* Principles */}
      <section>
        <div style={{
          borderRadius: 8, border: `1px solid ${T.border}`,
          padding: "20px 24px", background: T.bgCard,
        }}>
          <div style={{
            fontSize: 10, fontWeight: 600, color: T.textDim,
            textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 14,
            fontFamily: T.mono,
          }}>
            Principles
          </div>
          {[
            { title: "Neutral", desc: "No customer can pay to influence scores, weights, thresholds, or methodology timing." },
            { title: "Deterministic", desc: "Same inputs always produce the same outputs. No discretionary adjustments." },
            { title: "Versioned", desc: "All methodology changes are announced in advance, timestamped, and retroactively reproducible." },
            { title: "Composable", desc: "SII is designed as a programmable primitive — machine-readable, on-chain verifiable, and integratable into protocol logic." },
          ].map((p, i) => (
            <div
              key={i}
              style={{
                padding: "10px 0",
                borderBottom: i < 3 ? `1px solid ${T.border}` : "none",
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 600, color: T.textBright, fontFamily: T.sans }}>
                {p.title}
              </div>
              <div style={{ fontSize: 12, color: T.textMuted, marginTop: 3, fontFamily: T.sans, lineHeight: 1.5 }}>
                {p.desc}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// FOOTER
// ═══════════════════════════════════════════════════════════════════

function Footer() {
  return (
    <footer
      style={{
        padding: "16px 24px",
        borderTop: `1px solid ${T.border}`,
        display: "flex", justifyContent: "space-between", alignItems: "center",
        fontSize: 10, color: T.textDim, fontFamily: T.mono,
      }}
    >
      <span>Basis Protocol · Stablecoin Integrity Index</span>
      <span>Risk surfaces for on-chain finance · basisprotocol.xyz</span>
    </footer>
  );
}

// ═══════════════════════════════════════════════════════════════════
// APP
// ═══════════════════════════════════════════════════════════════════

export default function App() {
  const [view, setView] = useState("rankings");
  const [selectedCoin, setSelectedCoin] = useState(null);
  const { data: scores, loading, error, ts } = useScores();

  const handleSelect = useCallback((coinId) => {
    setSelectedCoin(coinId);
    setView("detail");
    window.scrollTo(0, 0);
  }, []);

  const handleBack = useCallback(() => {
    setView("rankings");
    setSelectedCoin(null);
  }, []);

  const handleSetView = useCallback((v) => {
    setView(v);
    if (v !== "detail") setSelectedCoin(null);
    window.scrollTo(0, 0);
  }, []);

  return (
    <div style={{ minHeight: "100vh", background: T.bg, color: T.text, fontFamily: T.sans }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Instrument+Sans:wght@400;500;600;700&family=Newsreader:ital,wght@0,400;0,600;1,400&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html { background: ${T.bg}; }
        body { background: ${T.bg}; }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: ${T.bg}; }
        ::-webkit-scrollbar-thumb { background: ${T.borderLight}; border-radius: 3px; }
        button { font-family: inherit; }
        button:hover { opacity: 0.88; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>

      <Header view={view} setView={handleSetView} ts={ts} />

      <main style={{ animation: "fadeIn 0.3s ease" }}>
        {view === "rankings" && (
          <RankingsView scores={scores} loading={loading} onSelect={handleSelect} />
        )}
        {view === "detail" && selectedCoin && (
          <DetailView coinId={selectedCoin} onBack={handleBack} />
        )}
        {view === "methodology" && <MethodologyView />}
      </main>

      <Footer />
    </div>
  );
}
