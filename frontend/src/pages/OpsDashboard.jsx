import { useState, useEffect, useCallback } from "react";

/**
 * Operations Hub Dashboard — founder's single operating surface.
 * Four modules: Pipeline Health, Action Queue, Target Tracker, Content Feed + Fundraise.
 * Protected by admin key (stored in localStorage or query param).
 */

const T = {
  paper: "#f5f2ec",
  paperWarm: "#f0ece3",
  ink: "#0a0a0a",
  inkMid: "#3a3a3a",
  inkLight: "#6a6a6a",
  inkFaint: "#9a9a9a",
  ruleMid: "#c8c4bc",
  ruleLight: "#e0ddd6",
  accent: "#c0392b",
  mono: "'IBM Plex Mono', monospace",
  sans: "'IBM Plex Sans', system-ui, sans-serif",
};

function getAdminKey() {
  const params = new URLSearchParams(window.location.search);
  return params.get("key") || localStorage.getItem("ops_admin_key") || "";
}

function setAdminKey(key) {
  localStorage.setItem("ops_admin_key", key);
}

async function opsFetch(path, opts = {}) {
  const key = getAdminKey();
  const resp = await fetch(path, {
    ...opts,
    headers: { "x-admin-key": key, "Content-Type": "application/json", ...(opts.headers || {}) },
  });
  if (resp.status === 401) throw new Error("unauthorized");
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  return resp.json();
}

// ─── Status indicators ───────────────────────────────────────────────

function StatusDot({ status }) {
  const colors = { healthy: "#27ae60", degraded: "#f39c12", down: "#e74c3c" };
  return (
    <span style={{
      display: "inline-block", width: 8, height: 8, borderRadius: "50%",
      background: colors[status] || "#999", marginRight: 6,
    }} />
  );
}

function StageBadge({ stage }) {
  const colors = {
    not_started: "#999", recognition: "#3498db", familiarity: "#2980b9",
    direct: "#8e44ad", evaluating: "#f39c12", trying: "#e67e22",
    binding: "#27ae60", archived: "#7f8c8d",
  };
  return (
    <span style={{
      fontSize: 10, fontFamily: T.mono, padding: "2px 6px", borderRadius: 3,
      background: (colors[stage] || "#999") + "22", color: colors[stage] || "#999",
      border: `1px solid ${colors[stage] || "#999"}44`,
    }}>
      {(stage || "unknown").replace(/_/g, " ")}
    </span>
  );
}

function TierBadge({ tier }) {
  const labels = { 1: "T1", 2: "T2", 3: "T3" };
  const colors = { 1: "#e74c3c", 2: "#f39c12", 3: "#95a5a6" };
  return (
    <span style={{
      fontSize: 9, fontFamily: T.mono, fontWeight: 600, padding: "1px 4px",
      borderRadius: 2, background: colors[tier] || "#999", color: "#fff",
      marginRight: 6,
    }}>
      {labels[tier] || `T${tier}`}
    </span>
  );
}

// ─── Auth Gate ────────────────────────────────────────────────────────

function AuthGate({ onAuth }) {
  const [key, setKey] = useState("");
  return (
    <div style={{ padding: 40, textAlign: "center", fontFamily: T.sans }}>
      <h2 style={{ fontFamily: T.mono, marginBottom: 16, fontWeight: 600, fontSize: 16 }}>
        Basis Operations Hub
      </h2>
      <p style={{ color: T.inkLight, fontSize: 13, marginBottom: 16 }}>Enter admin key to access</p>
      <input
        type="password"
        value={key}
        onChange={(e) => setKey(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onAuth(key)}
        placeholder="Admin key"
        style={{
          fontFamily: T.mono, fontSize: 13, padding: "8px 12px", border: `1px solid ${T.ruleMid}`,
          background: T.paper, width: 280, marginRight: 8,
        }}
      />
      <button
        onClick={() => onAuth(key)}
        style={{
          fontFamily: T.mono, fontSize: 12, padding: "8px 16px", border: `2px solid ${T.ink}`,
          background: T.ink, color: T.paper, cursor: "pointer",
        }}
      >
        Enter
      </button>
    </div>
  );
}

// ─── Pipeline Health ──────────────────────────────────────────────────

function HealthPanel({ health }) {
  if (!health || health.length === 0) {
    return <div style={{ color: T.inkFaint, fontSize: 12 }}>No health data. Run a health check first.</div>;
  }
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 8 }}>
      {health.map((h) => (
        <div key={h.system} style={{
          padding: "8px 10px", border: `1px solid ${T.ruleLight}`, background: T.paperWarm,
          fontSize: 11, fontFamily: T.mono,
        }}>
          <StatusDot status={h.status} />
          <strong>{h.system.replace(/_/g, " ")}</strong>
          <div style={{ color: T.inkLight, fontSize: 10, marginTop: 4 }}>
            {h.details && typeof h.details === "object"
              ? Object.entries(h.details).slice(0, 3).map(([k, v]) => (
                  <div key={k}>{k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}</div>
                ))
              : null}
            {h.checked_at && <div style={{ color: T.inkFaint, marginTop: 2 }}>checked: {new Date(h.checked_at).toLocaleTimeString()}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Action Queue ─────────────────────────────────────────────────────

function ActionQueue({ queue, onDecide }) {
  if (!queue || queue.length === 0) {
    return <div style={{ color: T.inkFaint, fontSize: 12 }}>No pending actions in queue.</div>;
  }
  return (
    <div>
      {queue.map((item) => (
        <div key={item.id} style={{
          padding: "10px 12px", borderBottom: `1px solid ${T.ruleLight}`, fontSize: 12,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontFamily: T.mono, marginBottom: 4 }}>
                {item.target_name} — {item.source_type}
              </div>
              <div style={{ fontWeight: 500, marginBottom: 4 }}>{item.title}</div>
              {item.bridge_text && (
                <div style={{ color: T.inkMid, fontSize: 11, marginBottom: 4 }}>
                  Bridge: {item.bridge_text}
                </div>
              )}
              {item.draft_comment && (
                <div style={{
                  background: T.paperWarm, padding: "6px 8px", fontSize: 11,
                  border: `1px solid ${T.ruleLight}`, marginBottom: 6, whiteSpace: "pre-wrap",
                }}>
                  {item.draft_comment}
                </div>
              )}
              <div style={{ fontSize: 10, color: T.inkFaint }}>
                {item.comment_type && <span>type: {item.comment_type} · </span>}
                {item.relevance_score != null && <span>relevance: {item.relevance_score} · </span>}
                {item.engagement_action && <span>action: {item.engagement_action}</span>}
              </div>
            </div>
            <div style={{ display: "flex", gap: 4, marginLeft: 12, flexShrink: 0 }}>
              {["approved", "skipped"].map((d) => (
                <button key={d} onClick={() => onDecide(item.id, d)} style={{
                  fontSize: 10, fontFamily: T.mono, padding: "4px 8px",
                  border: `1px solid ${T.ruleMid}`, background: d === "approved" ? "#27ae6022" : T.paper,
                  cursor: "pointer",
                }}>
                  {d === "approved" ? "Approve" : "Skip"}
                </button>
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Target Tracker ───────────────────────────────────────────────────

function TargetTracker({ targets, onSelect }) {
  return (
    <div>
      {(targets || []).map((t) => (
        <div key={t.id} onClick={() => onSelect(t.id)} style={{
          padding: "6px 10px", borderBottom: `1px solid ${T.ruleLight}`, fontSize: 12,
          display: "flex", alignItems: "center", gap: 8, cursor: "pointer",
        }}>
          <TierBadge tier={t.tier} />
          <div style={{ flex: 1, fontFamily: T.mono, fontWeight: 500 }}>{t.name}</div>
          <StageBadge stage={t.pipeline_stage} />
          <div style={{ fontSize: 10, color: T.inkFaint, minWidth: 100, textAlign: "right" }}>
            {t.next_action || "—"}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Fundraise Panel ──────────────────────────────────────────────────

function FundraisePanel({ data }) {
  if (!data) return null;
  const { investors, milestones: ms, raise: raiseInfo } = data;
  return (
    <div>
      {raiseInfo && (
        <div style={{ fontSize: 11, fontFamily: T.mono, color: T.inkMid, marginBottom: 10 }}>
          {raiseInfo.target} at {raiseInfo.valuation} · Target: {raiseInfo.timing}
        </div>
      )}
      {ms && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4 }}>
            Seed Triggers: {ms.met}/{ms.total} met (need {ms.threshold})
          </div>
          {(ms.milestones || []).map((m, i) => (
            <div key={i} style={{ fontSize: 11, fontFamily: T.mono, padding: "2px 0" }}>
              <span style={{ marginRight: 6 }}>{m.met ? "\u2705" : "\u274C"}</span>
              {m.name}
              {m.current != null && <span style={{ color: T.inkFaint }}> ({m.current}/{m.target})</span>}
            </div>
          ))}
        </div>
      )}
      <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4 }}>Investor Pipeline</div>
      {(investors || []).map((inv) => (
        <div key={inv.id} style={{
          fontSize: 11, fontFamily: T.mono, padding: "3px 0",
          display: "flex", gap: 8, borderBottom: `1px solid ${T.ruleLight}`,
        }}>
          <TierBadge tier={inv.tier} />
          <div style={{ flex: 1 }}>{inv.name}</div>
          <span style={{ color: T.inkLight }}>{(inv.stage || "").replace(/_/g, " ")}</span>
          <span style={{ color: T.inkFaint, fontSize: 10 }}>{inv.next_action || "—"}</span>
        </div>
      ))}
    </div>
  );
}

// ─── Content Feed ─────────────────────────────────────────────────────

function ContentFeed({ feed }) {
  if (!feed || feed.length === 0) {
    return <div style={{ color: T.inkFaint, fontSize: 12 }}>No content scraped yet.</div>;
  }
  return (
    <div>
      {feed.slice(0, 20).map((item) => (
        <div key={item.id} style={{
          padding: "6px 10px", borderBottom: `1px solid ${T.ruleLight}`, fontSize: 11,
        }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span style={{ fontFamily: T.mono, fontWeight: 500, minWidth: 100 }}>{item.target_name}</span>
            <span style={{ color: T.inkLight, fontSize: 10 }}>{item.source_type}</span>
            <span style={{ flex: 1 }}>{item.title || item.source_url}</span>
            {item.bridge_found != null && (
              <span style={{ fontSize: 10, color: item.bridge_found ? "#27ae60" : T.inkFaint }}>
                bridge: {item.bridge_found ? "YES" : "NO"}
              </span>
            )}
          </div>
          {item.content_summary && (
            <div style={{ color: T.inkMid, fontSize: 10, marginTop: 2 }}>{item.content_summary}</div>
          )}
        </div>
      ))}
    </div>
  );
}

// ─── Target Detail ────────────────────────────────────────────────────

function TargetDetail({ targetId, onBack }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    opsFetch(`/api/ops/targets/${targetId}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [targetId]);

  if (error) return <div style={{ color: T.accent }}>Error: {error}</div>;
  if (!data) return <div style={{ color: T.inkFaint, fontSize: 12 }}>Loading...</div>;

  const { target: t, contacts, recent_content, engagement_log, latest_exposure } = data;
  return (
    <div>
      <button onClick={onBack} style={{
        border: "none", background: "transparent", cursor: "pointer",
        fontFamily: T.mono, fontSize: 11, color: T.inkLight, marginBottom: 12,
      }}>
        &larr; Back to targets
      </button>
      <h3 style={{ fontFamily: T.mono, fontSize: 16, marginBottom: 4 }}>{t.name}</h3>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <TierBadge tier={t.tier} />
        <StageBadge stage={t.pipeline_stage} />
        {t.track && <span style={{ fontSize: 10, color: T.inkLight }}>track: {t.track}</span>}
        <span style={{ fontSize: 10, color: T.inkLight }}>type: {t.type}</span>
      </div>

      {t.worldview_summary && (
        <div style={{ fontSize: 12, marginBottom: 12, lineHeight: 1.5 }}>
          <strong>Worldview:</strong> {t.worldview_summary}
        </div>
      )}
      {t.gap && <div style={{ fontSize: 12, marginBottom: 8 }}><strong>Gap:</strong> {t.gap}</div>}
      {t.first_wedge && <div style={{ fontSize: 12, marginBottom: 8 }}><strong>First wedge:</strong> {t.first_wedge}</div>}
      {t.landmine && <div style={{ fontSize: 12, marginBottom: 8 }}><strong>Landmine:</strong> {t.landmine}</div>}
      {t.positioning && <div style={{ fontSize: 12, marginBottom: 12 }}><strong>Positioning:</strong> {t.positioning}</div>}

      {contacts && contacts.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <h4 style={{ fontFamily: T.mono, fontSize: 12, marginBottom: 4 }}>Contacts</h4>
          {contacts.map((c) => (
            <div key={c.id} style={{ fontSize: 11, padding: "2px 0" }}>
              <strong>{c.name}</strong> — {c.role}
              {c.twitter_handle && <span style={{ color: T.inkLight }}> {c.twitter_handle}</span>}
            </div>
          ))}
        </div>
      )}

      {recent_content && recent_content.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <h4 style={{ fontFamily: T.mono, fontSize: 12, marginBottom: 4 }}>Recent Content</h4>
          {recent_content.map((c) => (
            <div key={c.id} style={{ fontSize: 11, padding: "3px 0", borderBottom: `1px solid ${T.ruleLight}` }}>
              <div>{c.title || c.source_url}</div>
              {c.bridge_found != null && (
                <span style={{ fontSize: 10, color: c.bridge_found ? "#27ae60" : T.inkFaint }}>
                  bridge: {c.bridge_found ? "YES" : "NO"}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {engagement_log && engagement_log.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <h4 style={{ fontFamily: T.mono, fontSize: 12, marginBottom: 4 }}>Engagement Log</h4>
          {engagement_log.map((e) => (
            <div key={e.id} style={{ fontSize: 11, padding: "3px 0", borderBottom: `1px solid ${T.ruleLight}` }}>
              <span style={{ fontFamily: T.mono }}>{e.action_type}</span>
              {e.channel && <span style={{ color: T.inkLight }}> via {e.channel}</span>}
              {e.content && <div style={{ color: T.inkMid, fontSize: 10, marginTop: 2 }}>{e.content}</div>}
            </div>
          ))}
        </div>
      )}

      {latest_exposure && (
        <div>
          <h4 style={{ fontFamily: T.mono, fontSize: 12, marginBottom: 4 }}>Latest Exposure Report</h4>
          <pre style={{ fontSize: 10, fontFamily: T.mono, whiteSpace: "pre-wrap", background: T.paperWarm, padding: 8 }}>
            {latest_exposure.report_markdown}
          </pre>
        </div>
      )}
    </div>
  );
}

// ─── Section wrapper ──────────────────────────────────────────────────

function Section({ title, actions, children }) {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "6px 10px", background: T.ink, color: T.paper, cursor: "pointer",
      }} onClick={() => setCollapsed(!collapsed)}>
        <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 600, letterSpacing: 1 }}>
          {collapsed ? "\u25B6" : "\u25BC"} {title}
        </span>
        <div style={{ display: "flex", gap: 4 }} onClick={(e) => e.stopPropagation()}>
          {actions}
        </div>
      </div>
      {!collapsed && (
        <div style={{ border: `1px solid ${T.ruleMid}`, borderTop: "none", padding: "8px 0" }}>
          {children}
        </div>
      )}
    </div>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────────────

export default function OpsDashboard() {
  const [authed, setAuthed] = useState(!!getAdminKey());
  const [health, setHealth] = useState([]);
  const [queue, setQueue] = useState([]);
  const [targets, setTargets] = useState([]);
  const [fundraise, setFundraise] = useState(null);
  const [feed, setFeed] = useState([]);
  const [contentItems, setContentItems] = useState([]);
  const [selectedTarget, setSelectedTarget] = useState(null);
  const [tab, setTab] = useState("dashboard");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, q, t, f, cf, ci] = await Promise.all([
        opsFetch("/api/ops/health").catch(() => ({ health: [] })),
        opsFetch("/api/ops/queue").catch(() => ({ queue: [] })),
        opsFetch("/api/ops/targets").catch(() => ({ targets: [] })),
        opsFetch("/api/ops/fundraise/dashboard").catch(() => null),
        opsFetch("/api/ops/content/feed?limit=30").catch(() => ({ feed: [] })),
        opsFetch("/api/ops/content/items").catch(() => ({ items: [] })),
      ]);
      setHealth(h.health || []);
      setQueue(q.queue || []);
      setTargets(t.targets || []);
      setFundraise(f);
      setFeed(cf.feed || []);
      setContentItems(ci.items || []);
    } catch (e) {
      if (e.message === "unauthorized") {
        setAuthed(false);
        localStorage.removeItem("ops_admin_key");
      } else {
        setError(e.message);
      }
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (authed) load();
  }, [authed, load]);

  const handleAuth = (key) => {
    setAdminKey(key);
    setAuthed(true);
  };

  const handleDecide = async (contentId, decision) => {
    try {
      await opsFetch(`/api/ops/content/${contentId}/decide`, {
        method: "POST",
        body: JSON.stringify({ decision }),
      });
      setQueue((prev) => prev.filter((q) => q.id !== contentId));
    } catch (e) {
      setError(e.message);
    }
  };

  const handleRunHealthCheck = async () => {
    try {
      const result = await opsFetch("/api/ops/health/check", { method: "POST" });
      setHealth(result.checks || []);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleSeed = async () => {
    try {
      await opsFetch("/api/ops/seed", { method: "POST" });
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleMigrate = async () => {
    try {
      await opsFetch("/api/ops/migrate", { method: "POST" });
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  if (!authed) return <AuthGate onAuth={handleAuth} />;

  if (selectedTarget) {
    return (
      <div style={{ minHeight: "100vh", background: T.paper, fontFamily: T.sans, padding: "20px 24px" }}>
        <div style={{ maxWidth: 900, margin: "0 auto" }}>
          <TargetDetail targetId={selectedTarget} onBack={() => setSelectedTarget(null)} />
        </div>
      </div>
    );
  }

  const healthSummary = health.length > 0
    ? `${health.filter((h) => h.status === "healthy").length}/${health.length} healthy`
    : "no data";
  const warnings = health.filter((h) => h.status !== "healthy");

  return (
    <div style={{ minHeight: "100vh", background: T.paper, fontFamily: T.sans }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
        * { box-sizing: border-box; }
      `}</style>

      <div style={{ maxWidth: 1000, margin: "0 auto", padding: "16px 20px" }}>
        {/* Header */}
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          marginBottom: 16, borderBottom: `3px solid ${T.ink}`, paddingBottom: 8,
        }}>
          <div>
            <h1 style={{ fontFamily: T.mono, fontSize: 16, fontWeight: 700, letterSpacing: 1 }}>
              BASIS OPERATIONS HUB
            </h1>
            <div style={{ fontFamily: T.mono, fontSize: 10, color: T.inkFaint, marginTop: 2 }}>
              {new Date().toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
              {loading && " · loading..."}
            </div>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button onClick={handleMigrate} style={{ fontSize: 10, fontFamily: T.mono, padding: "4px 8px", border: `1px solid ${T.ruleMid}`, background: T.paper, cursor: "pointer" }}>
              Migrate
            </button>
            <button onClick={handleSeed} style={{ fontSize: 10, fontFamily: T.mono, padding: "4px 8px", border: `1px solid ${T.ruleMid}`, background: T.paper, cursor: "pointer" }}>
              Seed
            </button>
            <button onClick={load} style={{ fontSize: 10, fontFamily: T.mono, padding: "4px 8px", border: `1px solid ${T.ruleMid}`, background: T.paper, cursor: "pointer" }}>
              Refresh
            </button>
            <a href="/" style={{ fontSize: 10, fontFamily: T.mono, padding: "4px 8px", border: `1px solid ${T.ruleMid}`, background: T.paper, textDecoration: "none", color: T.ink, display: "flex", alignItems: "center" }}>
              SII Dashboard
            </a>
          </div>
        </div>

        {error && (
          <div style={{ padding: "8px 12px", background: "#e74c3c22", border: "1px solid #e74c3c44", fontSize: 12, marginBottom: 12, color: T.accent }}>
            {error}
            <button onClick={() => setError(null)} style={{ marginLeft: 8, border: "none", background: "transparent", cursor: "pointer" }}>&times;</button>
          </div>
        )}

        {/* Tabs */}
        <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
          {["dashboard", "targets", "fundraise", "content"].map((t) => (
            <button key={t} onClick={() => setTab(t)} style={{
              fontFamily: T.mono, fontSize: 11, padding: "4px 0", border: "none",
              background: "transparent", cursor: "pointer", fontWeight: tab === t ? 700 : 400,
              color: tab === t ? T.ink : T.inkLight,
              borderBottom: tab === t ? `2px solid ${T.ink}` : "2px solid transparent",
            }}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>

        {/* Dashboard tab */}
        {tab === "dashboard" && (
          <>
            <Section
              title="PIPELINE HEALTH"
              actions={
                <button onClick={handleRunHealthCheck} style={{
                  fontSize: 9, fontFamily: T.mono, padding: "2px 6px",
                  border: `1px solid ${T.paper}44`, background: "transparent",
                  color: T.paper, cursor: "pointer",
                }}>
                  Run Check
                </button>
              }
            >
              <div style={{ padding: "0 10px" }}>
                <div style={{ fontSize: 11, fontFamily: T.mono, color: T.inkMid, marginBottom: 8 }}>
                  {healthSummary}
                  {warnings.length > 0 && (
                    <span style={{ color: "#f39c12" }}> · {warnings.length} warning(s): {warnings.map((w) => w.system).join(", ")}</span>
                  )}
                </div>
                <HealthPanel health={health} />
              </div>
            </Section>

            <Section title={`ACTION QUEUE (${queue.length} items)`}>
              <ActionQueue queue={queue} onDecide={handleDecide} />
            </Section>

            <Section title={`TARGET TRACKER (${targets.filter((t) => t.tier <= 2).length} active)`}>
              <TargetTracker
                targets={targets.filter((t) => t.tier <= 2)}
                onSelect={setSelectedTarget}
              />
            </Section>

            <Section title="RECENT TARGET CONTENT">
              <div style={{ padding: "0 10px" }}>
                <ContentFeed feed={feed} />
              </div>
            </Section>
          </>
        )}

        {/* Targets tab */}
        {tab === "targets" && (
          <>
            <Section title="TIER 1 — ACTIVE PURSUIT">
              <TargetTracker targets={targets.filter((t) => t.tier === 1)} onSelect={setSelectedTarget} />
            </Section>
            <Section title="TIER 2 — MONITORING">
              <TargetTracker targets={targets.filter((t) => t.tier === 2)} onSelect={setSelectedTarget} />
            </Section>
            <Section title="TIER 3 — WATCH LIST">
              <TargetTracker targets={targets.filter((t) => t.tier === 3)} onSelect={setSelectedTarget} />
            </Section>
          </>
        )}

        {/* Fundraise tab */}
        {tab === "fundraise" && (
          <Section title="FUNDRAISE PIPELINE">
            <div style={{ padding: "0 10px" }}>
              <FundraisePanel data={fundraise} />
            </div>
          </Section>
        )}

        {/* Content tab */}
        {tab === "content" && (
          <>
            <Section title="CONTENT ITEMS">
              <div style={{ padding: "0 10px" }}>
                {contentItems.length === 0 ? (
                  <div style={{ color: T.inkFaint, fontSize: 12 }}>No content items yet.</div>
                ) : (
                  contentItems.map((item) => (
                    <div key={item.id} style={{
                      fontSize: 11, padding: "4px 0", borderBottom: `1px solid ${T.ruleLight}`,
                      display: "flex", gap: 8,
                    }}>
                      <span style={{ fontFamily: T.mono, fontSize: 10, color: T.inkLight, minWidth: 60 }}>{item.type}</span>
                      <span style={{ flex: 1 }}>{item.title || "(untitled)"}</span>
                      <StageBadge stage={item.status} />
                      {item.scheduled_for && (
                        <span style={{ fontSize: 10, color: T.inkFaint }}>
                          {new Date(item.scheduled_for).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  ))
                )}
              </div>
            </Section>
            <Section title="TARGET CONTENT FEED">
              <div style={{ padding: "0 10px" }}>
                <ContentFeed feed={feed} />
              </div>
            </Section>
          </>
        )}

        {/* Footer */}
        <div style={{ fontFamily: T.mono, fontSize: 10, color: T.inkFaint, textAlign: "center", marginTop: 24, paddingBottom: 16 }}>
          Basis Protocol · Operations Hub · Internal Use Only
        </div>
      </div>
    </div>
  );
}
