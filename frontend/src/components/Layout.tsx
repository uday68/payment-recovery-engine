import React, { useState, useEffect } from "react";
import { recoveryApi } from "../api";

export type PageId =
  | "overview"
  | "live-recovery"
  | "payments"
  | "experiments"
  | "ai-decisions"
  | "policies"
  | "system-health"
  | "audit-log"
  | "audit-search";

interface LayoutProps {
  currentPage: PageId;
  setCurrentPage: (page: PageId) => void;
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({
  currentPage,
  setCurrentPage,
  children,
}) => {
  const [streamRate, setStreamRate] = useState("1,840/s");
  const [p99Latency, setP99Latency] = useState("2.14ms");
  const [clusterStatus, setClusterStatus] = useState("PRODUCTION CLUSTER (:8080 & :8000 LIVE)");
  const [activeNodesText, setActiveNodesText] = useState("3/3 Nodes Active");
  const [mabCohortCount, setMabCohortCount] = useState(3);
  const [policyCount, setPolicyCount] = useState(4);
  const [modelVersion, setModelVersion] = useState("v2.4.1 (RF-Production)");
  const [searchQuery, setSearchQuery] = useState("");
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notificationsRead, setNotificationsRead] = useState(false);

  const fetchGlobalHeaderTelemetry = () => {
    recoveryApi
      .getLiveStreamStatus()
      .then((data) => {
        if (data) {
          if (data.streaming_rate) setStreamRate(data.streaming_rate);
          if (data.decision_p99_latency_ms) setP99Latency(data.decision_p99_latency_ms);
        }
      })
      .catch(() => {});

    recoveryApi
      .getSystemHealth()
      .then((data) => {
        if (data) {
          if (data.p99_execution_time) setP99Latency(data.p99_execution_time);
          if (data.node_status) {
            setActiveNodesText(`1 Node (${data.node_status.goroutines} goroutines)`);
            setClusterStatus(`FASTAPI & GO EXECUTOR (${data.node_status.status})`);
          }
        }
      })
      .catch(() => {});

    recoveryApi
      .getAIModelHealth()
      .then((data) => {
        if (data && data.model_name) {
          setModelVersion(data.model_name.includes("RandomForest") ? "v2.4.1 (RandomForest)" : data.model_name);
        }
      })
      .catch(() => {});

    recoveryApi
      .getMABExperiment()
      .then((data) => {
        if (data && data.active_arms_count) {
          setMabCohortCount(data.active_arms_count);
        }
      })
      .catch(() => {});

    recoveryApi
      .getPolicies()
      .then((data) => {
        if (data && data.length > 0) {
          setPolicyCount(data.length);
        }
      })
      .catch(() => {});
  };

  useEffect(() => {
    fetchGlobalHeaderTelemetry();
    const interval = setInterval(fetchGlobalHeaderTelemetry, 6000);
    return () => clearInterval(interval);
  }, []);

  const handleSearchSubmit = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && searchQuery.trim()) {
      setCurrentPage("payments");
    }
  };

  const getNavClass = (page: PageId) => {
    if (currentPage === page) {
      return "flex items-center justify-between px-space-sm py-space-xs rounded-lg transition-colors bg-surface-container-high text-on-surface border-l-2 border-primary font-body-md text-body-md cursor-pointer";
    }
    return "flex items-center justify-between px-space-sm py-space-xs rounded-lg text-on-surface-variant hover:bg-surface-container hover:text-on-surface transition-colors font-body-md text-body-md cursor-pointer";
  };

  return (
    <div className="bg-background font-body-md text-body-md text-on-surface antialiased min-h-screen">
      {/* Sidebar */}
      <aside className="fixed left-0 top-0 h-full w-64 bg-surface-container-lowest z-50 flex flex-col justify-between shadow-[0_1px_8px_rgba(0,0,0,0.5)]">
        <div className="flex flex-col flex-1 overflow-y-auto">
          {/* Logo Header */}
          <div className="h-14 px-space-base flex items-center gap-space-sm bg-surface-container-low">
            <div className="w-8 h-8 rounded-lg bg-surface-container-high flex items-center justify-center text-primary">
              <span className="material-symbols-outlined text-[18px]">security</span>
            </div>
            <div className="flex flex-col min-w-0">
              <span className="font-label-caps text-label-caps tracking-widest text-on-surface truncate uppercase font-semibold">
                Recovery Control
              </span>
              <span className="font-badge-label text-badge-label text-secondary truncate">
                TOWER CORE • LIVE
              </span>
            </div>
          </div>

          {/* Navigation Groups */}
          <div className="p-space-base flex flex-col gap-space-lg">
            {/* Group 1: Recovery */}
            <div className="flex flex-col gap-space-xs">
              <span className="px-space-xs font-label-caps text-label-caps uppercase text-outline">
                Recovery
              </span>
              <nav className="flex flex-col gap-space-2xs">
                <div
                  className={getNavClass("overview")}
                  onClick={() => setCurrentPage("overview")}
                >
                  <div className="flex items-center gap-space-sm">
                    <span className="material-symbols-outlined text-[16px]">grid_view</span>
                    <span>Overview</span>
                  </div>
                </div>
                <div
                  className={getNavClass("live-recovery")}
                  onClick={() => setCurrentPage("live-recovery")}
                >
                  <div className="flex items-center gap-space-sm">
                    <span className="material-symbols-outlined text-[16px]">monitoring</span>
                    <span>Live Recovery</span>
                  </div>
                  <span className="px-space-xs py-space-2xs rounded-lg bg-secondary-container text-on-secondary-container font-badge-label text-badge-label font-semibold">
                    {streamRate}
                  </span>
                </div>
                <div
                  className={getNavClass("payments")}
                  onClick={() => setCurrentPage("payments")}
                >
                  <div className="flex items-center gap-space-sm">
                    <span className="material-symbols-outlined text-[16px]">credit_card</span>
                    <span>Payments Forensics</span>
                  </div>
                </div>
                <div
                  className={getNavClass("experiments")}
                  onClick={() => setCurrentPage("experiments")}
                >
                  <div className="flex items-center gap-space-sm">
                    <span className="material-symbols-outlined text-[16px]">science</span>
                    <span>Experiments</span>
                  </div>
                  <span className="px-space-xs py-space-2xs rounded-lg bg-surface-container-high text-on-surface-variant font-badge-label text-badge-label">
                    {mabCohortCount} Cohorts
                  </span>
                </div>
              </nav>
            </div>

            {/* Group 2: Intelligence */}
            <div className="flex flex-col gap-space-xs">
              <span className="px-space-xs font-label-caps text-label-caps uppercase text-outline">
                Intelligence
              </span>
              <nav className="flex flex-col gap-space-2xs">
                <div
                  className={getNavClass("ai-decisions")}
                  onClick={() => setCurrentPage("ai-decisions")}
                >
                  <div className="flex items-center gap-space-sm">
                    <span className="material-symbols-outlined text-[16px]">psychology</span>
                    <span>AI Decisions</span>
                  </div>
                  <span className="px-space-xs py-space-2xs rounded-lg bg-primary/10 text-primary font-badge-label text-badge-label">
                    Bayesian
                  </span>
                </div>
                <div
                  className={getNavClass("payments")}
                  onClick={() => setCurrentPage("payments")}
                >
                  <div className="flex items-center gap-space-sm">
                    <span className="material-symbols-outlined text-[16px]">query_stats</span>
                    <span>Failure Analysis</span>
                  </div>
                </div>
              </nav>
            </div>

            {/* Group 3: Operations */}
            <div className="flex flex-col gap-space-xs">
              <span className="px-space-xs font-label-caps text-label-caps uppercase text-outline">
                Operations
              </span>
              <nav className="flex flex-col gap-space-2xs">
                <div
                  className={getNavClass("policies")}
                  onClick={() => setCurrentPage("policies")}
                >
                  <div className="flex items-center gap-space-sm">
                    <span className="material-symbols-outlined text-[16px]">policy</span>
                    <span>Policies</span>
                  </div>
                  <span className="px-space-xs py-space-2xs rounded-lg bg-tertiary-container text-on-tertiary-container font-badge-label text-badge-label">
                    {policyCount} Enforced
                  </span>
                </div>
                <div
                  className={getNavClass("system-health")}
                  onClick={() => setCurrentPage("system-health")}
                >
                  <div className="flex items-center gap-space-sm">
                    <span className="material-symbols-outlined text-[16px]">dns</span>
                    <span>System Health</span>
                  </div>
                  <span className="px-space-xs py-space-2xs rounded-lg bg-surface-container-high text-secondary font-badge-label text-badge-label">
                    99.99% SLA
                  </span>
                </div>
              </nav>
            </div>

            {/* Group 4: Developer */}
            <div className="flex flex-col gap-space-xs">
              <span className="px-space-xs font-label-caps text-label-caps uppercase text-outline">
                Developer
              </span>
              <nav className="flex flex-col gap-space-2xs">
                <div
                  className={getNavClass("audit-log")}
                  onClick={() => setCurrentPage("audit-log")}
                >
                  <div className="flex items-center gap-space-sm">
                    <span className="material-symbols-outlined text-[16px]">receipt_long</span>
                    <span>Audit Log</span>
                  </div>
                  <span className="px-space-xs py-space-2xs rounded-lg bg-secondary/10 text-secondary font-mono-code text-[10px]">
                    WAL
                  </span>
                </div>
                <div
                  className={getNavClass("audit-search")}
                  onClick={() => setCurrentPage("audit-search")}
                >
                  <div className="flex items-center gap-space-sm">
                    <span className="material-symbols-outlined text-[16px]">search</span>
                    <span>Audit Search</span>
                  </div>
                  <span className="px-space-xs py-space-2xs rounded-lg bg-primary/10 text-primary font-mono-code text-[10px]">
                    ES/SQL
                  </span>
                </div>
              </nav>
            </div>
          </div>
        </div>

        {/* Sidebar Footer */}
        <div className="p-space-base flex flex-col gap-space-sm bg-surface-container-lowest">
          <div className="flex items-center justify-between px-space-sm py-space-xs rounded-lg bg-surface-container-low">
            <div className="flex items-center gap-space-xs">
              <span className="w-2 h-2 rounded-full bg-secondary animate-pulse"></span>
              <span className="font-badge-label text-badge-label text-on-surface">{activeNodesText}</span>
            </div>
            <span className="font-mono-code text-mono-code text-secondary">OK</span>
          </div>
          <div className="flex items-center justify-between px-space-sm py-space-xs rounded-lg bg-surface-container cursor-pointer">
            <div className="flex items-center gap-space-xs min-w-0">
              <span className="material-symbols-outlined text-[14px] text-tertiary">sync_alt</span>
              <span className="font-mono-code text-mono-code text-on-surface truncate">{modelVersion}</span>
            </div>
            <span className="font-badge-label text-badge-label text-secondary uppercase font-semibold">PROD</span>
          </div>
          <div className="flex items-center gap-space-sm pt-space-xs">
            <div className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center text-primary">
              <span className="material-symbols-outlined text-[18px]">badge</span>
            </div>
            <div className="flex flex-col min-w-0">
              <span className="font-body-sm text-body-sm text-on-surface truncate">Control Tower Core</span>
              <span className="font-label-caps text-label-caps text-outline truncate">HDFC / ICICI Switch</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="pl-64">
        {/* Top Header */}
        <header className="fixed top-0 left-64 right-0 h-14 bg-surface-container-lowest/80 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.5)] z-40 flex items-center justify-between px-layout-margin-desktop">
          <div className="flex items-center gap-space-md">
            <div className="flex items-center gap-space-xs font-mono-code text-mono-code text-on-surface-variant">
              <span className="text-primary font-semibold">cluster</span>
              <span>/</span>
              <span className="text-on-surface">recovery-engine</span>
            </div>
            <div className="px-space-xs py-space-2xs rounded-lg bg-surface-container-high text-secondary font-label-caps text-label-caps uppercase tracking-wider flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-secondary animate-ping"></span>
              <span>{clusterStatus}</span>
            </div>
          </div>
          <div className="flex items-center gap-space-lg">
            <div className="relative flex items-center">
              <span className="material-symbols-outlined absolute left-space-sm text-outline text-[16px]">
                search
              </span>
              <input
                className="w-80 h-8 pl-8 pr-4 rounded-lg bg-surface-container-low text-on-surface placeholder-outline font-mono-code text-mono-code focus:outline-none focus:bg-surface-container-high"
                placeholder="Search payment ID (e.g. pay_9281)..."
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleSearchSubmit}
              />
            </div>
            <div className="flex items-center gap-space-sm px-space-sm py-space-2xs rounded-lg bg-surface-container-low">
              <div className="flex items-center gap-space-2xs">
                <span className="w-2 h-2 rounded-full bg-secondary animate-pulse"></span>
                <span className="font-badge-label text-badge-label text-secondary font-semibold">KAFKA LIVE</span>
              </div>
              <span className="text-outline text-[10px]">|</span>
              <span className="font-badge-label text-badge-label text-on-surface-variant font-mono-code">
                Throughput: {streamRate}
              </span>
              <span className="text-outline text-[10px]">|</span>
              <span className="font-badge-label text-badge-label text-on-surface-variant font-mono-code">
                P99: {p99Latency}
              </span>
              <span className="text-outline text-[10px]">|</span>
              <span className="font-badge-label text-badge-label text-outline font-mono-code">
                {modelVersion.slice(0, 10)}
              </span>
            </div>
            <div className="flex items-center gap-space-md">
              <div className="relative">
                <button
                  type="button"
                  aria-label="Open notifications"
                  aria-expanded={notificationsOpen}
                  onClick={() => {
                    setNotificationsOpen((open) => !open);
                    setNotificationsRead(true);
                  }}
                  className="relative flex items-center cursor-pointer text-on-surface-variant hover:text-on-surface transition-colors"
                >
                <span className="material-symbols-outlined text-on-surface-variant hover:text-on-surface text-[20px]">
                  notifications
                </span>
                  {!notificationsRead && (
                    <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-secondary" />
                  )}
                </button>
                {notificationsOpen && (
                  <div className="absolute right-0 top-9 w-80 rounded-lg border border-surface-container-high bg-surface-container-lowest shadow-2xl z-50">
                    <div className="flex items-center justify-between px-space-sm py-space-sm border-b border-surface-container-high">
                      <span className="font-label-caps text-label-caps text-on-surface uppercase">Notifications</span>
                      <button
                        type="button"
                        onClick={() => setNotificationsOpen(false)}
                        className="text-outline hover:text-on-surface"
                        aria-label="Close notifications"
                      >
                        <span className="material-symbols-outlined text-[16px]">close</span>
                      </button>
                    </div>
                    <div className="p-space-sm flex flex-col gap-space-xs">
                      <div className="flex gap-space-xs p-space-xs rounded bg-surface-container">
                        <span className="material-symbols-outlined text-secondary text-[18px]">check_circle</span>
                        <div className="min-w-0">
                          <div className="font-body-sm text-body-sm text-on-surface">Recovery engine online</div>
                          <div className="font-label-caps text-label-caps text-outline">{clusterStatus}</div>
                        </div>
                      </div>
                      <div className="flex gap-space-xs p-space-xs rounded bg-surface-container">
                        <span className="material-symbols-outlined text-primary text-[18px]">monitoring</span>
                        <div className="min-w-0">
                          <div className="font-body-sm text-body-sm text-on-surface">Kafka stream active</div>
                          <div className="font-label-caps text-label-caps text-outline">Throughput: {streamRate}</div>
                        </div>
                      </div>
                      <div className="flex gap-space-xs p-space-xs rounded bg-surface-container">
                        <span className="material-symbols-outlined text-tertiary text-[18px]">model_training</span>
                        <div className="min-w-0">
                          <div className="font-body-sm text-body-sm text-on-surface">Model serving</div>
                          <div className="font-label-caps text-label-caps text-outline">{modelVersion}</div>
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-space-xs px-space-sm pb-space-sm">
                      <button
                        type="button"
                        onClick={() => { setCurrentPage("system-health"); setNotificationsOpen(false); }}
                        className="flex-1 px-space-xs py-space-xs rounded bg-surface-container-high text-on-surface font-label-caps text-label-caps hover:bg-surface-container transition-colors"
                      >
                        System Health
                      </button>
                      <button
                        type="button"
                        onClick={() => { setCurrentPage("live-recovery"); setNotificationsOpen(false); }}
                        className="flex-1 px-space-xs py-space-xs rounded bg-primary text-on-primary font-label-caps text-label-caps hover:bg-primary-container transition-colors"
                      >
                        Live Recovery
                      </button>
                    </div>
                  </div>
                )}
              </div>
              <div className="flex items-center gap-space-xs pl-space-sm">
                <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center">
                  <span className="material-symbols-outlined text-on-primary text-[18px]">person</span>
                </div>
                <div className="hidden xl:flex flex-col">
                  <span className="font-body-sm text-body-sm text-on-surface">FinOps Core</span>
                  <span className="font-label-caps text-label-caps text-outline">Autonomous Mode</span>
                </div>
              </div>
            </div>
          </div>
        </header>

        {/* Page Body */}
        <main className="w-full pt-14 px-layout-margin-desktop bg-background min-h-screen">
          {children}
        </main>
      </div>
    </div>
  );
};

export default Layout;