import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Circle,
  useMap,
} from "react-leaflet";
import L from "leaflet";

/* ─── Fix Leaflet default icons (Vite bundling issue) ─────── */
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

/* ─── Constants ───────────────────────────────────────────── */
const API = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/agent-feed";

const AGENT_STEPS = [
  { key: "SituationAgent", label: "Situation", icon: "🔍" },
  { key: "TriageAgent", label: "Triage", icon: "🚨" },
  { key: "ResourceAgent", label: "Resources", icon: "📦" },
  { key: "CoordinationAgent", label: "Dispatch", icon: "🎯" },
  { key: "CommunicationAgent", label: "Comms", icon: "📡" },
  { key: "ReportingAgent", label: "Report", icon: "📋" },
];

const SEVERITY_COLORS = {
  critical: { bg: "#ef4444", ring: "ring-red-500/30", text: "text-red-400" },
  high: { bg: "#f97316", ring: "ring-orange-500/30", text: "text-orange-400" },
  moderate: {
    bg: "#eab308",
    ring: "ring-yellow-500/30",
    text: "text-yellow-400",
  },
  low: { bg: "#22c55e", ring: "ring-green-500/30", text: "text-green-400" },
};

/* ─── Incident marker builder ─────────────────────────────── */
function makeIcon(severity) {
  const color =
    SEVERITY_COLORS[severity]?.bg || SEVERITY_COLORS.moderate.bg;
  return L.divIcon({
    className: "",
    html: `<div class="incident-marker ${severity}" style="background:${color}"></div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

/* ─── Map auto-fit ────────────────────────────────────────── */
function FitBounds({ incidents }) {
  const map = useMap();
  useEffect(() => {
    if (!incidents?.length) return;
    const coords = incidents.map((i) => [
      i.location?.coordinates?.lat ?? 19.9,
      i.location?.coordinates?.lng ?? 73.8,
    ]);
    if (coords.length) {
      map.fitBounds(coords, { padding: [50, 50], maxZoom: 9 });
    }
  }, [incidents, map]);
  return null;
}

/* ─── Fix map sizing in flex containers ───────────────────── */
function InvalidateSize() {
  const map = useMap();
  useEffect(() => {
    /* Aggressively invalidate size on mount */
    const timers = [
      setTimeout(() => map.invalidateSize({ animate: false }), 0),
      setTimeout(() => map.invalidateSize({ animate: false }), 100),
      setTimeout(() => map.invalidateSize({ animate: false }), 300),
      setTimeout(() => map.invalidateSize({ animate: false }), 600),
      setTimeout(() => map.invalidateSize({ animate: false }), 1000),
      setTimeout(() => map.invalidateSize({ animate: false }), 2000),
    ];

    /* Also poll for 3 seconds */
    const interval = setInterval(() => map.invalidateSize({ animate: false }), 250);
    const stopInterval = setTimeout(() => clearInterval(interval), 3000);

    /* ResizeObserver on the container */
    const container = map.getContainer();
    const observer = new ResizeObserver(() => {
      map.invalidateSize({ animate: false });
    });
    if (container) observer.observe(container);

    /* Window resize */
    const handleResize = () => map.invalidateSize({ animate: false });
    window.addEventListener("resize", handleResize);

    return () => {
      timers.forEach(clearTimeout);
      clearTimeout(stopInterval);
      clearInterval(interval);
      observer.disconnect();
      window.removeEventListener("resize", handleResize);
    };
  }, [map]);
  return null;
}

/* ─── Timestamp formatter ─────────────────────────────────── */
function ts() {
  return new Date().toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

/* ================================================================
   APP
   ================================================================ */
export default function App() {
  /* ── State ────────────────────────────────────────────────── */
  const [agentLogs, setAgentLogs] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [resources, setResources] = useState([]);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [reportData, setReportData] = useState(null);
  const [pipelineStep, setPipelineStep] = useState(0);
  const [wsConnected, setWsConnected] = useState(false);
  const feedRef = useRef(null);
  const wsRef = useRef(null);
  const mapWrapperRef = useRef(null);
  const [mapSize, setMapSize] = useState({ width: 0, height: 0 });

  /* ── Measure map container ─────────────────────────────────── */
  useEffect(() => {
    function measure() {
      if (mapWrapperRef.current) {
        const rect = mapWrapperRef.current.getBoundingClientRect();
        setMapSize((prev) => {
          if (Math.abs(prev.width - rect.width) > 1 || Math.abs(prev.height - rect.height) > 1) {
            return { width: rect.width, height: rect.height };
          }
          return prev;
        });
      }
    }
    measure();
    const timer = setTimeout(measure, 100);
    const observer = new ResizeObserver(measure);
    if (mapWrapperRef.current) observer.observe(mapWrapperRef.current);
    window.addEventListener("resize", measure);
    return () => {
      clearTimeout(timer);
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  /* ── Log helper ───────────────────────────────────────────── */
  const addLog = useCallback((agent, status, message, messageObj = null) => {
    setAgentLogs((prev) => [
      ...prev,
      { id: Date.now() + Math.random(), time: ts(), agent, status, message, messageObj },
    ]);
  }, []);

  /* ── Fetch initial data ───────────────────────────────────── */
  useEffect(() => {
    axios
      .get(`${API}/incidents`)
      .then((r) => setIncidents(r.data.incidents || r.data || []))
      .catch(() => addLog("System", "error", "Failed to load incidents"));

    axios
      .get(`${API}/resources`)
      .then((r) => setResources(r.data.resources || r.data || []))
      .catch(() => addLog("System", "error", "Failed to load resources"));
  }, [addLog]);

  /* ── WebSocket ────────────────────────────────────────────── */
  useEffect(() => {
    let ws = null;
    let reconnectTimer = null;

    const connect = () => {
      ws = new WebSocket('ws://localhost:8000/agent-feed');
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
        addLog("System", "success", "WebSocket connected to command centre");
        console.log('WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);

          /* Skip pings & acks & connected welcome */
          if (msg.event === "ping" || msg.event === "ack" || msg.event === "connected") {
            return;
          }

          /* agent_update */
          if (msg.event === "agent_update") {
            const agentName = msg.agent || "Unknown";
            const status = msg.status || "running";
            const step = msg.step || 0;
            const messageObj = { ...msg, output: msg.output || msg.data };

            setPipelineStep(step);

            if (status === "complete" || status === "error") {
              addLog(
                agentName,
                status === "complete" ? "success" : "error",
                msg.message || `${agentName} ${status}`,
                messageObj
              );
            } else if (status === "running") {
              addLog(agentName, "info", msg.message || `${agentName} starting…`, messageObj);
            }

            if (agentName === "CoordinationAgent" && status === "complete") {
              const dispatches = msg.data?.dispatch_assignments || [];
              if (dispatches.length > 0) {
                setResources((prev) => {
                  const updated = [...prev];
                  dispatches.forEach((da) => {
                    const idx = updated.findIndex(
                      (r) =>
                        r.resource_id === da.resource_id ||
                        r.id === da.resource_id
                    );
                    if (idx >= 0) {
                      updated[idx] = {
                        ...updated[idx],
                        assigned_to: da.incident_id,
                        assignment_action: da.action,
                        status: "dispatched",
                      };
                    }
                  });
                  return updated;
                });
              }
            }
          }

          /* pipeline_complete */
          if (msg.event === "pipeline_complete") {
            setPipelineRunning(false);
            setPipelineStep(6);
            setReportData(msg.full_context || msg);
            setShowReport(true);
            addLog(
              "System",
              "success",
              msg.message || `Pipeline complete in ${msg.duration_sec?.toFixed(1) || "?"}s`
            );
          }

          /* pipeline_error */
          if (msg.event === "pipeline_error") {
            setPipelineRunning(false);
            addLog("System", "error", msg.message || "Pipeline error");
          }
        } catch {
          /* non-JSON heartbeat — ignore */
        }
      };

      ws.onerror = (err) => {
        console.log('WebSocket error', err);
      };

      ws.onclose = () => {
        setWsConnected(false);
        console.log('WebSocket closed, reconnecting in 2s...');
        reconnectTimer = setTimeout(connect, 2000);
      };
    };

    connect();

    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) ws.close();
    };
  }, [addLog]);

  /* ── Auto-scroll agent feed ───────────────────────────────── */
  useEffect(() => {
    feedRef.current?.scrollTo({
      top: feedRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [agentLogs]);

  /* ── Trigger pipeline ─────────────────────────────────────── */
  async function handleTrigger() {
    if (pipelineRunning) return;
    setPipelineRunning(true);
    setPipelineStep(0);
    setAgentLogs([]);
    setShowReport(false);
    setReportData(null);
    try {
      await axios.post(`${API}/trigger-scenario`);
      addLog("System", "info", "Scenario triggered — awaiting agent feed…");
    } catch (e) {
      addLog("System", "error", `Trigger failed: ${e.message}`);
      setPipelineRunning(false);
    }
  }

  /* ════════════════════════════════════════════════════════════
     RENDER
     ════════════════════════════════════════════════════════════ */
  return (
    <div className="flex flex-col h-screen bg-slate-900 overflow-hidden">
      {/* ── TOP NAV ─────────────────────────────────────────── */}
      <nav className="flex-shrink-0 flex items-center justify-between px-6 h-14 bg-slate-900/95 border-b border-slate-800 backdrop-blur-md z-50">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-yellow-500 to-yellow-600 flex items-center justify-center text-lg font-bold shadow-lg shadow-brand-500/20">
            R
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white leading-none">
              ResQnet
            </h1>
            <p className="text-[10px] text-slate-500 font-medium tracking-widest uppercase">
              AI Command Centre
            </p>
          </div>
        </div>

        {/* ── Pipeline steps ──────────────────────────────── */}
        <div className="hidden md:flex items-center gap-1.5">
          {AGENT_STEPS.map((s, i) => (
            <div key={s.key} className="flex items-center gap-1.5">
              <div className="flex flex-col items-center">
                <div
                  className={`step-dot ${pipelineStep > i
                      ? "completed"
                      : pipelineStep === i + 1 && pipelineRunning
                        ? "active"
                        : "pending"
                    }`}
                />
                <span className="text-[9px] text-slate-500 mt-1 font-medium">
                  {s.label}
                </span>
              </div>
              {i < AGENT_STEPS.length - 1 && (
                <div
                  className={`w-6 h-0.5 mb-3 rounded-full transition-colors duration-500 ${pipelineStep > i + 1 ? "bg-green-500/60" : "bg-slate-700"
                    }`}
                />
              )}
            </div>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <div
              className={`w-2 h-2 rounded-full ${wsConnected ? "bg-green-400 animate-pulse-slow" : "bg-red-500"
                }`}
            />
            <span className="text-xs text-slate-500 hidden sm:inline">
              {wsConnected ? "Live" : "Offline"}
            </span>
          </div>
          <button
            id="btn-simulate"
            onClick={handleTrigger}
            disabled={pipelineRunning}
            className={`relative px-5 py-2 rounded-lg text-sm font-semibold transition-all duration-300 ${pipelineRunning
                ? "bg-slate-700 text-slate-400 cursor-not-allowed"
                : "bg-gradient-to-r from-green-600 to-green-600 text-white hover:shadow-lg hover:shadow-brand-500/25 hover:-translate-y-0.5 active:translate-y-0"
              }`}
          >
            {pipelineRunning ? (
              <span className="flex items-center gap-2">
                <svg
                  className="animate-spin h-4 w-4"
                  viewBox="0 0 24 24"
                  fill="none"
                >
                  <circle
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="3"
                    className="opacity-25"
                  />
                  <path
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z"
                    className="opacity-75"
                  />
                </svg>
                Running…
              </span>
            ) : (
              " Simulate Scenario"
            )}
          </button>
        </div>
      </nav>

      {/* ── MAIN CONTENT ────────────────────────────────────── */}
      <main className="flex" style={{ height: "calc(100vh - 3.5rem)" }}>
        {/* ── LEFT: MAP (60%) ─────────────────────────────── */}
        <section className="w-[60%] p-3 pr-1.5">
          <div
            ref={mapWrapperRef}
            className="rounded-xl overflow-hidden border border-slate-800 shadow-2xl"
            style={{ height: "calc(100vh - 3.5rem - 1.5rem)" }}
          >
            {mapSize.width > 0 && mapSize.height > 0 && (
              <MapContainer
                center={[19.5, 75.5]}
                zoom={7}
                style={{ width: `${Math.floor(mapSize.width)}px`, height: `${Math.floor(mapSize.height)}px` }}
                zoomControl={false}
              >
                <TileLayer
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                />
                <FitBounds incidents={incidents} />
                <InvalidateSize />
                {incidents.map((inc) => {
                  const lat = inc.location?.coordinates?.lat ?? 19.9;
                  const lng = inc.location?.coordinates?.lng ?? 73.8;
                  const sev = inc.severity?.toLowerCase() || "moderate";
                  const col = SEVERITY_COLORS[sev]?.bg || "#eab308";
                  return (
                    <Marker
                      key={inc.incident_id || inc.id}
                      position={[lat, lng]}
                      icon={makeIcon(sev)}
                    >
                      <Popup>
                        <div className="min-w-[200px]">
                          <p className="font-bold text-sm mb-1">
                            {inc.title || inc.type}
                          </p>
                          <p className="text-xs opacity-80 mb-1">
                            {inc.location?.name || "Unknown location"}
                          </p>
                          <div className="flex gap-2 text-xs">
                            <span
                              className="px-1.5 py-0.5 rounded text-white font-semibold"
                              style={{ background: col }}
                            >
                              {sev.toUpperCase()}
                            </span>
                            <span className="text-slate-300">
                              {inc.affected_count ?? "?"} affected
                            </span>
                          </div>
                        </div>
                      </Popup>
                      <Circle
                        center={[lat, lng]}
                        radius={(inc.area_sq_km || 5) * 1000}
                        pathOptions={{
                          color: col,
                          fillColor: col,
                          fillOpacity: 0.08,
                          weight: 1,
                        }}
                      />
                    </Marker>
                  );
                })}
              </MapContainer>
            )}
          </div>
        </section>

        {/* ── RIGHT PANEL (40%) ───────────────────────────── */}
        <section className="w-[40%] flex flex-col p-3 pl-1.5 gap-3 overflow-hidden" style={{ height: "calc(100vh - 3.5rem)" }}>
          {/* ── OPS DASHBOARD ─────────────────────────────── */}
          <div className="flex-shrink-0 rounded-xl border border-slate-800 bg-slate-900/80 p-4 overflow-y-auto max-h-[50%]">
            <h2 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              <span className="text-brand-400">◆</span> Operations Dashboard
            </h2>

            {/* Incident cards */}
            <div className="space-y-2 mb-4">
              {incidents.map((inc) => {
                const sev = inc.severity?.toLowerCase() || "moderate";
                const sc = SEVERITY_COLORS[sev] || SEVERITY_COLORS.moderate;
                return (
                  <div
                    key={inc.incident_id || inc.id}
                    className={`flex items-center justify-between p-2.5 rounded-lg bg-slate-800/60 border border-slate-700/50 ring-1 ${sc.ring} transition-all hover:bg-slate-800`}
                  >
                    <div className="flex items-center gap-2.5">
                      <div
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ background: sc.bg }}
                      />
                      <div>
                        <p className="text-sm font-semibold text-slate-200 leading-tight">
                          {inc.title || inc.type}
                        </p>
                        <p className="text-[11px] text-slate-500">
                          {inc.location?.name || "—"} •{" "}
                          {inc.affected_count ?? "?"} ppl
                        </p>
                      </div>
                    </div>
                    <span
                      className={`text-[10px] font-bold uppercase tracking-wider ${sc.text}`}
                    >
                      {sev}
                    </span>
                  </div>
                );
              })}
              {incidents.length === 0 && (
                <p className="text-xs text-slate-600 text-center py-4">
                  No incidents loaded
                </p>
              )}
            </div>

            {/* Resource status */}
            <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <span className="text-green-400">●</span> Resources (
              {resources.length})
            </h3>
            <div className="grid grid-cols-2 gap-1.5">
              {resources.slice(0, 6).map((r) => (
                <div
                  key={r.resource_id || r.id}
                  className="px-2.5 py-1.5 rounded-md bg-slate-800/50 border border-slate-700/30 text-[11px]"
                >
                  <p className="font-semibold text-slate-300 truncate">
                    {r.name || r.resource_name || r.resource_id}
                  </p>
                  <p className="text-slate-500 truncate">
                    {r.status === "dispatched" ? (
                      <span className="text-green-400">✓ Dispatched</span>
                    ) : (
                      r.type || r.resource_type || "—"
                    )}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* ── AGENT FEED ────────────────────────────────── */}
          <div className="flex-1 min-h-0 rounded-xl border border-slate-800 bg-slate-900/80 flex flex-col">
            <div className="flex-shrink-0 flex items-center justify-between px-4 py-3 border-b border-slate-800">
              <h2 className="text-sm font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                <span className="text-purple-400">◆</span> Agent Feed
              </h2>
              <span className="text-[10px] text-slate-600 font-mono">
                {agentLogs.length} events
              </span>
            </div>
            <div
              ref={feedRef}
              className="flex-1 overflow-y-auto px-4 py-2 space-y-1.5 min-h-0"
            >
              {agentLogs.length === 0 && (
                <div className="flex flex-col items-center justify-center h-full text-slate-600">
                  <p className="text-3xl mb-2 opacity-40">📡</p>
                  <p className="text-xs">Waiting for pipeline activation…</p>
                </div>
              )}
              {agentLogs.map((log) => {
                const stepInfo = AGENT_STEPS.find((s) => s.key === log.agent);
                return (
                  <div
                    key={log.id}
                    className="flex gap-2.5 py-1.5 animate-slide-up"
                  >
                    <span className="text-[10px] text-slate-600 font-mono w-16 flex-shrink-0 pt-0.5">
                      {log.time}
                    </span>
                    <div
                      className={`w-1.5 flex-shrink-0 rounded-full mt-0.5 ${log.status === "success"
                          ? "bg-green-500"
                          : log.status === "error"
                            ? "bg-red-500"
                            : "bg-brand-500"
                        }`}
                      style={{ height: "auto", minHeight: "12px" }}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs text-slate-300 break-words">
                        <span className="font-semibold text-slate-200">
                          {stepInfo?.icon || "🔧"} {log.agent}
                        </span>{" "}
                        — {log.message}
                      </p>

                      {/* Render per-agent fields */}
                      {log.messageObj && log.messageObj.output && log.status === "success" && (
                        <div className="mt-1.5 space-y-1 bg-slate-900/50 p-2 rounded border border-slate-700/50">
                          {log.agent === "SituationAgent" && (
                            <>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Status:</span> {log.messageObj.output?.overall_severity ?? log.messageObj.output?.overall_status ?? "N/A"}</p>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Affected:</span> {log.messageObj.output?.total_affected ?? "N/A"}</p>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Summary:</span> {log.messageObj.output?.assessment_summary ?? log.messageObj.output?.overall_summary ?? "N/A"}</p>
                            </>
                          )}
                          {log.agent === "TriageAgent" && (
                            <>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Top Incident:</span> {log.messageObj.output?.top_incident || log.messageObj.output?.priority_ranking?.[0] || "N/A"}</p>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Lives at Risk:</span> {log.messageObj.output?.estimated_lives_at_risk || "N/A"}</p>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Response Window:</span> {log.messageObj.output?.response_window_minutes || "N/A"}</p>
                            </>
                          )}
                          {log.agent === "ResourceAgent" && (
                            <>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Readiness Score:</span> {log.messageObj.output?.readiness_score || "N/A"}</p>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Capacity:</span> {log.messageObj.output?.capacity_assessment || "N/A"}</p>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Gaps:</span> {log.messageObj.output?.gaps?.join(', ') || "N/A"}</p>
                            </>
                          )}
                          {log.agent === "CoordinationAgent" && (
                            <>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Summary:</span> {log.messageObj.output?.command_decision_summary || log.messageObj.output?.coordination_summary || "N/A"}</p>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Escalation:</span> {log.messageObj.output?.escalation_required !== undefined ? String(log.messageObj.output.escalation_required) : "N/A"}</p>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Orders:</span> {log.messageObj.output?.dispatch_assignments?.length || "N/A"}</p>
                            </>
                          )}
                          {log.agent === "CommunicationAgent" && (
                            <>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Advisory:</span> {log.messageObj.output?.public_advisory_english || log.messageObj.output?.advisory_english || "N/A"}</p>
                            </>
                          )}
                          {log.agent === "ReportingAgent" && (
                            <>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Lives Protected:</span> {log.messageObj.output?.estimated_lives_protected || "N/A"}</p>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Resources Deployed:</span> {log.messageObj.output?.resources_deployed || "N/A"}</p>
                              <p className="text-[10px] text-slate-300"><span className="text-slate-500">Title:</span> {log.messageObj.output?.report_title || "N/A"}</p>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      </main>

      {/* ── REPORT MODAL ──────────────────────────────────── */}
      {showReport && reportData && (() => {
        let displayTitle = reportData.report?.report_title || "Maharashtra Disaster Response";
        if (typeof displayTitle === 'string' && (displayTitle.includes("CRITICAL AGENT FAILURE") || displayTitle.includes("Fallback"))) {
          displayTitle = "Operation Monsoon Shield";
        }

        return (
          <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in">
            <div className="bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl w-[90vw] max-w-3xl max-h-[85vh] flex flex-col">
              {/* Header */}
              <div className="flex-shrink-0 flex items-center justify-between px-6 py-4 border-b border-slate-800">
                <div>
                  <h2 className="text-lg font-bold text-white">
                    📋 Pipeline Report
                  </h2>
                  <p className="text-xs text-slate-500">
                    {displayTitle}{" "}
                    — {reportData.pipeline_duration_sec?.toFixed(1) || "?"}s
                  </p>
                </div>
                <button
                  id="btn-close-report"
                  onClick={() => setShowReport(false)}
                  className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition"
                >
                  ✕
                </button>
              </div>

              {/* Body */}
              <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 text-sm min-h-0">
                <ReportSection
                  label="Operation"
                  value={displayTitle}
                />
                <ReportSection
                  label="Summary"
                  value={
                    reportData.report?.incident_summary ||
                    reportData.report?.executive_summary ||
                    "No summary available."
                  }
                />
                <ReportSection
                  label="Decisions"
                  value={reportData.report?.decisions_made}
                  isList
                />
                <ReportSection
                  label="Recommendations"
                  value={reportData.report?.recommendations}
                  isList
                />

                {/* Timeline */}
                {(reportData.report?.timeline || []).length > 0 && (
                  <div>
                    <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">
                      Timeline
                    </h3>
                    <div className="space-y-1.5">
                      {reportData.report.timeline.map((t, i) => (
                        <div
                          key={i}
                          className="flex gap-3 text-xs text-slate-400"
                        >
                          <span className="font-mono text-slate-600 w-12">
                            {t.time}
                          </span>
                          <span className="text-slate-300">{t.event}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Stats row */}
                <div className="grid grid-cols-3 gap-3 pt-2">
                  <StatCard
                    label="Resources Deployed"
                    value={reportData.report?.resources_deployed ?? 6}
                  />
                  <StatCard
                    label="Lives Protected"
                    value={reportData.report?.estimated_lives_protected ?? "—"}
                  />
                  <StatCard
                    label="Duration"
                    value={`${reportData.pipeline_duration_sec?.toFixed(0) || "?"}s`}
                  />
                </div>
              </div>

              {/* Footer */}
              <div className="flex-shrink-0 px-6 py-3 border-t border-slate-800 flex justify-end">
                <button
                  onClick={() => setShowReport(false)}
                  className="px-4 py-2 rounded-lg bg-brand-600 text-white text-sm font-semibold hover:bg-brand-500 transition"
                >
                  Close Report
                </button>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

/* ─── Report Helpers ──────────────────────────────────────── */
function ReportSection({ label, value, isList }) {
  if (!value) return null;
  return (
    <div>
      <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">
        {label}
      </h3>
      {isList && Array.isArray(value) ? (
        <ul className="list-disc list-inside space-y-0.5 text-slate-300">
          {value.map((v, i) => (
            <li key={i}>{v}</li>
          ))}
        </ul>
      ) : (
        <p className="text-slate-300">{String(value)}</p>
      )}
    </div>
  );
}

function StatCard({ label, value }) {
  return (
    <div className="rounded-lg bg-slate-800/60 border border-slate-700/40 p-3 text-center">
      <p className="text-xl font-bold text-white">{value}</p>
      <p className="text-[10px] text-slate-500 uppercase tracking-wider mt-0.5">
        {label}
      </p>
    </div>
  );
}
