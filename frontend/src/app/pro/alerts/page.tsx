"use client";

import { useState, useEffect, useCallback } from "react";
import {
  getAlerts,
  markAlertRead,
  type AlertItem,
} from "@/lib/api-alerts";

// --- Helpers ---

function formatIst(iso: string): string {
  try {
    return new Date(iso).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return iso;
  }
}

function sourceBadgeColor(source: string): string {
  switch (source) {
    case "rs_analyzer":
      return "bg-teal-50 text-teal-700 border-teal-200";
    case "sector_analyst":
      return "bg-purple-50 text-purple-700 border-purple-200";
    case "mf_decisions":
      return "bg-amber-50 text-amber-700 border-amber-200";
    default:
      return "bg-gray-50 text-gray-600 border-gray-200";
  }
}

function sourceLabel(source: string): string {
  return source.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// --- Skeleton ---

function SkeletonCard() {
  return (
    <div className="bg-white border border-[#e4e4e8] rounded-lg p-5 animate-pulse">
      <div className="flex items-start gap-3 mb-3">
        <div className="h-5 bg-gray-200 rounded w-24" />
        <div className="h-5 bg-gray-100 rounded w-16" />
      </div>
      <div className="h-4 bg-gray-200 rounded w-full mb-2" />
      <div className="h-4 bg-gray-100 rounded w-4/5 mb-3" />
      <div className="h-3 bg-gray-100 rounded w-1/3" />
    </div>
  );
}

// --- AlertCard ---

interface AlertCardProps {
  alert: AlertItem;
  onMarkRead: (id: number) => Promise<void>;
}

function AlertCard({ alert, onMarkRead }: AlertCardProps) {
  const [marking, setMarking] = useState(false);
  const [markError, setMarkError] = useState<string | null>(null);

  async function handleMarkRead() {
    setMarking(true);
    setMarkError(null);
    try {
      await onMarkRead(alert.id);
    } catch (e) {
      setMarkError(e instanceof Error ? e.message : "Failed to mark as read");
    } finally {
      setMarking(false);
    }
  }

  return (
    <div
      data-testid="alert-card"
      className={`bg-white border border-[#e4e4e8] rounded-lg p-5 transition-colors ${
        !alert.is_read
          ? "border-l-4 border-l-[#1D9E75]"
          : "border-l-4 border-l-gray-200"
      }`}
    >
      {/* Top row: source badge + symbol + alert type */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span
          className={`inline-flex items-center text-xs px-2 py-0.5 rounded border font-medium ${sourceBadgeColor(alert.source)}`}
        >
          {sourceLabel(alert.source)}
        </span>

        {alert.symbol != null && (
          <span className="inline-flex items-center text-xs px-2 py-0.5 rounded border bg-slate-50 text-slate-700 border-slate-200 font-mono">
            {alert.symbol}
          </span>
        )}

        {alert.alert_type != null && (
          <span className="inline-flex items-center text-xs px-2 py-0.5 rounded border bg-blue-50 text-blue-700 border-blue-200 font-medium">
            {alert.alert_type.replace(/_/g, " ")}
          </span>
        )}

        {!alert.is_read && (
          <span className="inline-flex items-center text-xs px-2 py-0.5 rounded bg-[#1D9E75] text-white font-medium">
            Unread
          </span>
        )}
      </div>

      {/* Message */}
      {alert.message != null && (
        <p className="text-sm text-gray-700 mb-3 leading-relaxed">
          {alert.message}
        </p>
      )}

      {/* RS + quadrant row */}
      {(alert.rs_at_alert != null || alert.quadrant_at_alert != null) && (
        <div className="flex flex-wrap gap-3 mb-3 text-xs text-gray-500">
          {alert.rs_at_alert != null && (
            <span>
              RS:{" "}
              <span className="font-semibold text-gray-700">
                {alert.rs_at_alert}
              </span>
            </span>
          )}
          {alert.quadrant_at_alert != null && (
            <span>
              Quadrant:{" "}
              <span className="font-semibold text-gray-700">
                {alert.quadrant_at_alert}
              </span>
            </span>
          )}
        </div>
      )}

      {/* Footer: timestamp + mark-read button */}
      <div className="flex items-center justify-between border-t border-[#e4e4e8] pt-2 mt-2">
        <span className="text-xs text-gray-400">{formatIst(alert.created_at)}</span>

        <div className="flex items-center gap-2">
          {markError != null && (
            <span className="text-xs text-red-600">{markError}</span>
          )}
          {!alert.is_read && (
            <button
              data-testid="mark-read-btn"
              onClick={handleMarkRead}
              disabled={marking}
              className="text-xs text-[#1D9E75] border border-[#1D9E75] rounded px-2 py-0.5 hover:bg-teal-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {marking ? "Marking..." : "Mark as read"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Source options ---

const SOURCE_OPTIONS = [
  { value: "", label: "All sources" },
  { value: "rs_analyzer", label: "RS Analyzer" },
  { value: "sector_analyst", label: "Sector Analyst" },
  { value: "mf_decisions", label: "MF Decisions" },
];

// --- Main page ---

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await getAlerts({
        source: sourceFilter || undefined,
        unread: unreadOnly || undefined,
        limit: 50,
      });
      setAlerts(resp.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load alerts");
    } finally {
      setLoading(false);
    }
  }, [sourceFilter, unreadOnly]);

  useEffect(() => {
    loadAlerts();
  }, [loadAlerts]);

  async function handleMarkRead(id: number) {
    await markAlertRead(id);
    // Optimistic update: mark as read in local state
    setAlerts((prev) =>
      prev == null
        ? prev
        : prev.map((a) => (a.id === id ? { ...a, is_read: true } : a))
    );
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Sticky header */}
      <header className="border-b bg-white sticky top-0 z-10">
        <div className="max-w-[1600px] mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a href="/" className="text-xl font-bold tracking-tight">
              <span className="text-[#1D9E75]">ATLAS</span>
              <span className="text-gray-400 text-sm font-normal ml-2">Pro</span>
            </a>
            <nav className="flex items-center gap-1 text-sm text-gray-500 ml-2">
              <a href="/" className="hover:text-gray-800">
                Home
              </a>
              <span>/</span>
              <span className="text-gray-800 font-medium">Alerts</span>
            </nav>
          </div>
          <div className="text-xs text-gray-400">
            Jhaveri Intelligence Platform
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-4 py-6">
        {/* Page title */}
        <div className="mb-6">
          <h1 className="text-lg font-semibold text-gray-900">Alerts</h1>
          <p className="text-sm text-gray-500 mt-1">
            System-generated alerts from RS analyzer, sector analyst, and MF
            decision pipelines.
          </p>
        </div>

        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-3 mb-6 p-3 bg-gray-50 border border-[#e4e4e8] rounded-lg">
          <div>
            <label className="text-xs font-medium text-gray-600 mr-2">
              Source
            </label>
            <select
              data-testid="source-filter"
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              className="border border-[#e4e4e8] rounded px-2 py-1 text-sm focus:outline-none focus:border-[#1D9E75] bg-white"
            >
              {SOURCE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          <label
            data-testid="unread-filter"
            className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer"
          >
            <input
              type="checkbox"
              checked={unreadOnly}
              onChange={(e) => setUnreadOnly(e.target.checked)}
              className="accent-[#1D9E75]"
            />
            Unread only
          </label>
        </div>

        {/* Content */}
        {loading && (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {!loading && error != null && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
            {error}
            <button
              onClick={loadAlerts}
              className="ml-3 text-red-600 underline hover:no-underline"
            >
              Retry
            </button>
          </div>
        )}

        {!loading && error == null && alerts != null && alerts.length === 0 && (
          <div className="bg-gray-50 border border-[#e4e4e8] rounded-lg p-8 text-center text-sm text-gray-500">
            No alerts found.
          </div>
        )}

        {!loading && error == null && alerts != null && alerts.length > 0 && (
          <div className="space-y-3" data-testid="alert-list">
            <div className="text-xs text-gray-400 mb-2">
              {alerts.length} alert{alerts.length !== 1 ? "s" : ""}
            </div>
            {alerts.map((alert) => (
              <AlertCard
                key={alert.id}
                alert={alert}
                onMarkRead={handleMarkRead}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
