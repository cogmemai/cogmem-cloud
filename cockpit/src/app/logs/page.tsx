"use client";

import { useEffect, useState, useCallback } from "react";
import {
  SidebarInset,
  SidebarProvider,
} from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/dashboard/app-sidebar";
import { SiteHeader } from "@/components/dashboard/site-header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  IconRefresh,
  IconFilter,
  IconChevronDown,
  IconChevronRight,
  IconActivity,
  IconDatabase,
  IconBrain,
  IconTimeline,
  IconAlertCircle,
  IconInfoCircle,
  IconAlertTriangle,
} from "@tabler/icons-react";

// ─── Types ───────────────────────────────────────────────────────────────────

interface KosLogEntry {
  id?: string;
  agent: string;
  level: string;
  event_type: string;
  message: string;
  correlation_id: string;
  item_id?: string;
  passage_ids?: string[];
  entity_ids?: string[];
  duration_ms?: number;
  metadata?: Record<string, unknown>;
  created_at: string;
}

interface AuditLogEntry {
  id?: string;
  table_name: string;
  action: string;
  record_id?: string;
  data_before?: Record<string, unknown>;
  data_after?: Record<string, unknown>;
  created_at: string;
}

interface LogStats {
  kos_logs_total: number;
  audit_log_total: number;
  items_total: number;
  passages_total: number;
  entities_total: number;
  agents: Array<{ agent: string; count: number }>;
  levels: Array<{ level: string; count: number }>;
  audit_by_table: Array<{ table_name: string; action: string; count: number }>;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function levelColor(level: string) {
  switch (level?.toUpperCase()) {
    case "ERROR":
      return "destructive";
    case "WARN":
      return "secondary";
    case "INFO":
      return "default";
    case "DEBUG":
      return "outline";
    default:
      return "outline";
  }
}

function LevelIcon({ level }: { level: string }) {
  switch (level?.toUpperCase()) {
    case "ERROR":
      return <IconAlertCircle className="size-4 text-red-500" />;
    case "WARN":
      return <IconAlertTriangle className="size-4 text-yellow-500" />;
    default:
      return <IconInfoCircle className="size-4 text-blue-500" />;
  }
}

function actionColor(action: string) {
  switch (action) {
    case "CREATE":
      return "default";
    case "UPDATE":
      return "secondary";
    case "DELETE":
      return "destructive";
    default:
      return "outline";
  }
}

function formatTime(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      fractionalSecondDigits: 3,
    });
  } catch {
    return iso;
  }
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

// ─── Stats Cards ─────────────────────────────────────────────────────────────

function StatsCards({ stats }: { stats: LogStats | null }) {
  if (!stats) return null;

  const cards = [
    { label: "Pipeline Logs", value: stats.kos_logs_total, icon: IconActivity, color: "text-blue-500" },
    { label: "Audit Events", value: stats.audit_log_total, icon: IconDatabase, color: "text-purple-500" },
    { label: "Items", value: stats.items_total, icon: IconBrain, color: "text-green-500" },
    { label: "Passages", value: stats.passages_total, icon: IconTimeline, color: "text-orange-500" },
    { label: "Entities", value: stats.entities_total, icon: IconTimeline, color: "text-pink-500" },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {cards.map((c) => (
        <Card key={c.label} className="py-3">
          <CardContent className="flex items-center gap-3 px-4 py-0">
            <c.icon className={`size-8 ${c.color} shrink-0`} />
            <div>
              <p className="text-2xl font-bold tabular-nums">{c.value}</p>
              <p className="text-muted-foreground text-xs">{c.label}</p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ─── KOS Log Row ─────────────────────────────────────────────────────────────

function KosLogRow({ entry }: { entry: KosLogEntry }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-b last:border-b-0">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-muted/50 transition-colors"
      >
        <div className="mt-0.5 shrink-0">
          {expanded ? (
            <IconChevronDown className="size-4 text-muted-foreground" />
          ) : (
            <IconChevronRight className="size-4 text-muted-foreground" />
          )}
        </div>
        <LevelIcon level={entry.level} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={levelColor(entry.level)} className="text-[10px] px-1.5 py-0">
              {entry.level}
            </Badge>
            <Badge variant="outline" className="text-[10px] px-1.5 py-0 font-mono">
              {entry.agent}
            </Badge>
            <span className="text-[10px] text-muted-foreground font-mono">
              {entry.event_type}
            </span>
            {entry.duration_ms != null && (
              <span className="text-[10px] text-muted-foreground tabular-nums">
                {entry.duration_ms.toFixed(1)}ms
              </span>
            )}
          </div>
          <p className="text-sm mt-0.5 truncate">{entry.message}</p>
        </div>
        <span className="text-[10px] text-muted-foreground whitespace-nowrap shrink-0 tabular-nums">
          {formatTime(entry.created_at)}
        </span>
      </button>

      {expanded && (
        <div className="px-12 pb-3 space-y-2">
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
            <div>
              <span className="text-muted-foreground">Correlation ID:</span>{" "}
              <span className="font-mono">{truncate(entry.correlation_id, 36)}</span>
            </div>
            {entry.item_id && (
              <div>
                <span className="text-muted-foreground">Item ID:</span>{" "}
                <span className="font-mono">{truncate(entry.item_id, 36)}</span>
              </div>
            )}
            {entry.passage_ids && entry.passage_ids.length > 0 && (
              <div className="col-span-2">
                <span className="text-muted-foreground">Passages:</span>{" "}
                <span className="font-mono">{entry.passage_ids.length} passage(s)</span>
              </div>
            )}
            {entry.entity_ids && entry.entity_ids.length > 0 && (
              <div className="col-span-2">
                <span className="text-muted-foreground">Entities:</span>{" "}
                <span className="font-mono">{entry.entity_ids.length} entity(ies)</span>
              </div>
            )}
          </div>
          {entry.metadata && Object.keys(entry.metadata).length > 0 && (
            <div>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                Metadata
              </p>
              <pre className="text-xs bg-muted rounded-md p-2 overflow-x-auto max-h-48 font-mono">
                {JSON.stringify(entry.metadata, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Audit Log Row ───────────────────────────────────────────────────────────

function AuditLogRow({ entry }: { entry: AuditLogEntry }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-b last:border-b-0">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-muted/50 transition-colors"
      >
        <div className="mt-0.5 shrink-0">
          {expanded ? (
            <IconChevronDown className="size-4 text-muted-foreground" />
          ) : (
            <IconChevronRight className="size-4 text-muted-foreground" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Badge variant={actionColor(entry.action)} className="text-[10px] px-1.5 py-0">
              {entry.action}
            </Badge>
            <Badge variant="outline" className="text-[10px] px-1.5 py-0 font-mono">
              {entry.table_name}
            </Badge>
            {entry.record_id && (
              <span className="text-[10px] text-muted-foreground font-mono truncate">
                {truncate(entry.record_id, 50)}
              </span>
            )}
          </div>
        </div>
        <span className="text-[10px] text-muted-foreground whitespace-nowrap shrink-0 tabular-nums">
          {formatTime(entry.created_at)}
        </span>
      </button>

      {expanded && (
        <div className="px-12 pb-3 space-y-2">
          {entry.data_after && (
            <div>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                {entry.action === "UPDATE" ? "After" : "Data"}
              </p>
              <pre className="text-xs bg-muted rounded-md p-2 overflow-x-auto max-h-64 font-mono">
                {JSON.stringify(entry.data_after, null, 2)}
              </pre>
            </div>
          )}
          {entry.data_before && (
            <div>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                Before
              </p>
              <pre className="text-xs bg-muted rounded-md p-2 overflow-x-auto max-h-64 font-mono">
                {JSON.stringify(entry.data_before, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function LogsPage() {
  const [tab, setTab] = useState("pipeline");
  const [stats, setStats] = useState<LogStats | null>(null);
  const [kosLogs, setKosLogs] = useState<KosLogEntry[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [kosTotal, setKosTotal] = useState(0);
  const [auditTotal, setAuditTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  // Filters
  const [levelFilter, setLevelFilter] = useState<string>("all");
  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [tableFilter, setTableFilter] = useState<string>("all");
  const [actionFilter, setActionFilter] = useState<string>("all");
  const [correlationSearch, setCorrelationSearch] = useState("");

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch("/api/logs?type=stats");
      if (res.ok) setStats(await res.json());
    } catch {}
  }, []);

  const fetchKosLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ type: "kos_logs", limit: "200" });
      if (levelFilter !== "all") params.set("level", levelFilter);
      if (agentFilter !== "all") params.set("agent", agentFilter);
      if (correlationSearch) params.set("correlation_id", correlationSearch);
      const res = await fetch(`/api/logs?${params}`);
      if (res.ok) {
        const data = await res.json();
        setKosLogs(data.data || []);
        setKosTotal(data.total || 0);
      }
    } catch {}
    setLoading(false);
  }, [levelFilter, agentFilter, correlationSearch]);

  const fetchAuditLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ type: "audit_log", limit: "200" });
      if (tableFilter !== "all") params.set("table_name", tableFilter);
      if (actionFilter !== "all") params.set("action", actionFilter);
      const res = await fetch(`/api/logs?${params}`);
      if (res.ok) {
        const data = await res.json();
        setAuditLogs(data.data || []);
        setAuditTotal(data.total || 0);
      }
    } catch {}
    setLoading(false);
  }, [tableFilter, actionFilter]);

  const refreshAll = useCallback(() => {
    fetchStats();
    fetchKosLogs();
    fetchAuditLogs();
  }, [fetchStats, fetchKosLogs, fetchAuditLogs]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  // Auto-refresh every 10s
  useEffect(() => {
    const interval = setInterval(refreshAll, 10000);
    return () => clearInterval(interval);
  }, [refreshAll]);

  return (
    <SidebarProvider
      style={
        {
          "--sidebar-width": "calc(var(--spacing) * 72)",
          "--header-height": "calc(var(--spacing) * 12)",
        } as React.CSSProperties
      }
    >
      <AppSidebar variant="inset" />
      <SidebarInset>
        <SiteHeader />
        <div className="flex flex-1 flex-col">
          <div className="flex flex-col gap-4 p-4 lg:p-6">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold tracking-tight">KOS Logs</h1>
                <p className="text-muted-foreground text-sm">
                  Pipeline execution logs and database audit trail
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={refreshAll}
                disabled={loading}
                className="gap-1.5"
              >
                <IconRefresh className={`size-4 ${loading ? "animate-spin" : ""}`} />
                Refresh
              </Button>
            </div>

            {/* Stats */}
            <StatsCards stats={stats} />

            {/* Tabs */}
            <Tabs value={tab} onValueChange={setTab} className="flex-1">
              <TabsList className="w-full justify-start">
                <TabsTrigger value="pipeline" className="gap-1.5">
                  <IconActivity className="size-4" />
                  Pipeline Logs
                  {kosTotal > 0 && (
                    <Badge variant="secondary" className="ml-1 text-[10px] px-1.5 py-0">
                      {kosTotal}
                    </Badge>
                  )}
                </TabsTrigger>
                <TabsTrigger value="audit" className="gap-1.5">
                  <IconDatabase className="size-4" />
                  Audit Trail
                  {auditTotal > 0 && (
                    <Badge variant="secondary" className="ml-1 text-[10px] px-1.5 py-0">
                      {auditTotal}
                    </Badge>
                  )}
                </TabsTrigger>
              </TabsList>

              {/* Pipeline Logs Tab */}
              <TabsContent value="pipeline" className="mt-4 space-y-3">
                {/* Filters */}
                <div className="flex items-center gap-2 flex-wrap">
                  <IconFilter className="size-4 text-muted-foreground" />
                  <Select value={levelFilter} onValueChange={setLevelFilter}>
                    <SelectTrigger className="w-28 h-8 text-xs">
                      <SelectValue placeholder="Level" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Levels</SelectItem>
                      <SelectItem value="INFO">INFO</SelectItem>
                      <SelectItem value="WARN">WARN</SelectItem>
                      <SelectItem value="ERROR">ERROR</SelectItem>
                      <SelectItem value="DEBUG">DEBUG</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={agentFilter} onValueChange={setAgentFilter}>
                    <SelectTrigger className="w-44 h-8 text-xs">
                      <SelectValue placeholder="Agent" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Agents</SelectItem>
                      <SelectItem value="cloud_ingest">cloud_ingest</SelectItem>
                      <SelectItem value="chunk_agent">chunk_agent</SelectItem>
                      <SelectItem value="entity_extract_agent">entity_extract_agent</SelectItem>
                    </SelectContent>
                  </Select>
                  <Input
                    placeholder="Correlation ID..."
                    value={correlationSearch}
                    onChange={(e) => setCorrelationSearch(e.target.value)}
                    className="w-64 h-8 text-xs font-mono"
                  />
                </div>

                {/* Log entries */}
                <Card>
                  <CardHeader className="py-3 px-4">
                    <CardTitle className="text-sm font-medium">
                      Pipeline Execution Logs
                      <span className="text-muted-foreground font-normal ml-2">
                        ({kosLogs.length} of {kosTotal})
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    {kosLogs.length === 0 ? (
                      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                        <IconActivity className="size-10 mb-2 opacity-30" />
                        <p className="text-sm">No pipeline logs yet</p>
                        <p className="text-xs">Send a message in the Playground to generate logs</p>
                      </div>
                    ) : (
                      <div className="max-h-[600px] overflow-y-auto">
                        {kosLogs.map((entry, i) => (
                          <KosLogRow key={entry.id || i} entry={entry} />
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              {/* Audit Trail Tab */}
              <TabsContent value="audit" className="mt-4 space-y-3">
                {/* Filters */}
                <div className="flex items-center gap-2 flex-wrap">
                  <IconFilter className="size-4 text-muted-foreground" />
                  <Select value={tableFilter} onValueChange={setTableFilter}>
                    <SelectTrigger className="w-32 h-8 text-xs">
                      <SelectValue placeholder="Table" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Tables</SelectItem>
                      <SelectItem value="items">items</SelectItem>
                      <SelectItem value="passages">passages</SelectItem>
                      <SelectItem value="entities">entities</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={actionFilter} onValueChange={setActionFilter}>
                    <SelectTrigger className="w-28 h-8 text-xs">
                      <SelectValue placeholder="Action" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Actions</SelectItem>
                      <SelectItem value="CREATE">CREATE</SelectItem>
                      <SelectItem value="UPDATE">UPDATE</SelectItem>
                      <SelectItem value="DELETE">DELETE</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Audit entries */}
                <Card>
                  <CardHeader className="py-3 px-4">
                    <CardTitle className="text-sm font-medium">
                      Database Audit Trail
                      <span className="text-muted-foreground font-normal ml-2">
                        ({auditLogs.length} of {auditTotal})
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    {auditLogs.length === 0 ? (
                      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                        <IconDatabase className="size-10 mb-2 opacity-30" />
                        <p className="text-sm">No audit events yet</p>
                        <p className="text-xs">
                          Database changes to items, passages, and entities are logged automatically
                        </p>
                      </div>
                    ) : (
                      <div className="max-h-[600px] overflow-y-auto">
                        {auditLogs.map((entry, i) => (
                          <AuditLogRow key={entry.id || i} entry={entry} />
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
