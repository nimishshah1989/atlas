"use client";

import { useState, useEffect } from "react";
import {
  getWatchlists,
  syncWatchlistToTv,
  createWatchlist,
  deleteWatchlist,
  type WatchlistItem,
} from "@/lib/api-watchlists";

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

// --- Skeleton ---

function SkeletonCard() {
  return (
    <div className="bg-white border border-[#e4e4e8] rounded-lg p-5 animate-pulse">
      <div className="flex items-start justify-between mb-3">
        <div className="h-5 bg-gray-200 rounded w-40" />
        <div className="h-5 bg-gray-100 rounded w-20" />
      </div>
      <div className="flex flex-wrap gap-1 mb-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-5 bg-gray-100 rounded w-12" />
        ))}
      </div>
      <div className="h-8 bg-gray-100 rounded w-28 mt-3" />
    </div>
  );
}

// --- WatchlistCard ---

interface WatchlistCardProps {
  watchlist: WatchlistItem;
  onSync: (id: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}

function WatchlistCard({ watchlist, onSync, onDelete }: WatchlistCardProps) {
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const MAX_SHOWN = 5;
  const shownSymbols = watchlist.symbols.slice(0, MAX_SHOWN);
  const extraCount = watchlist.symbols.length - MAX_SHOWN;

  async function handleSync() {
    setSyncing(true);
    setSyncMsg(null);
    setSyncError(null);
    try {
      const resp = await onSync(watchlist.id);
      // onSync resolves after updating local state; show success from response
      void resp;
      setSyncMsg("Synced to TradingView");
    } catch (e) {
      setSyncError(
        e instanceof Error ? e.message : "Sync failed"
      );
    } finally {
      setSyncing(false);
    }
  }

  async function handleDelete() {
    if (!confirm(`Delete watchlist "${watchlist.name}"?`)) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await onDelete(watchlist.id);
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Delete failed");
      setDeleting(false);
    }
  }

  return (
    <div
      data-testid="watchlist-card"
      className="bg-white border border-[#e4e4e8] rounded-lg p-5 hover:border-[#1D9E75] transition-colors"
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h3 className="font-semibold text-gray-900">{watchlist.name}</h3>
          <span className="text-xs text-gray-500 mt-0.5 block">
            {watchlist.symbols.length} symbol
            {watchlist.symbols.length !== 1 ? "s" : ""}
          </span>
        </div>

        {/* TV-synced badge */}
        <span
          data-testid="tv-synced-badge"
          className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded border ${
            watchlist.tv_synced
              ? "bg-green-50 text-green-700 border-green-200"
              : "bg-gray-50 text-gray-500 border-gray-200"
          }`}
        >
          {watchlist.tv_synced ? "TV Synced" : "Not synced"}
        </span>
      </div>

      {/* Symbol chips */}
      {watchlist.symbols.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {shownSymbols.map((sym) => (
            <span
              key={sym}
              className="inline-flex items-center text-xs px-2 py-0.5 rounded border bg-slate-50 text-slate-700 border-slate-200 font-mono"
            >
              {sym}
            </span>
          ))}
          {extraCount > 0 && (
            <span className="inline-flex items-center text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-500">
              +{extraCount} more
            </span>
          )}
        </div>
      )}

      {watchlist.symbols.length === 0 && (
        <p className="text-xs text-gray-400 mb-3 italic">No symbols</p>
      )}

      {/* Timestamps */}
      <div className="text-xs text-gray-400 mb-3">
        Updated {formatIst(watchlist.updated_at)}
      </div>

      {/* Inline messages */}
      {syncMsg != null && (
        <div className="text-xs text-green-700 bg-green-50 border border-green-200 rounded px-2 py-1 mb-2">
          {syncMsg}
        </div>
      )}
      {syncError != null && (
        <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded px-2 py-1 mb-2">
          {syncError}
        </div>
      )}
      {deleteError != null && (
        <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded px-2 py-1 mb-2">
          {deleteError}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-2 pt-2 border-t border-[#e4e4e8]">
        <button
          data-testid="sync-tv-btn"
          onClick={handleSync}
          disabled={syncing || deleting}
          className="text-sm bg-[#1D9E75] text-white font-medium px-4 py-1.5 rounded hover:bg-[#178a63] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {syncing ? "Syncing..." : "Sync to TV"}
        </button>

        <button
          onClick={handleDelete}
          disabled={deleting || syncing}
          className="text-sm border border-red-200 text-red-600 font-medium px-3 py-1.5 rounded hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {deleting ? "Deleting..." : "Delete"}
        </button>
      </div>
    </div>
  );
}

// --- New watchlist form ---

interface NewWatchlistFormProps {
  onCreated: (wl: WatchlistItem) => void;
}

function NewWatchlistForm({ onCreated }: NewWatchlistFormProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [symbolsText, setSymbolsText] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  async function handleCreate() {
    const trimmedName = name.trim();
    if (!trimmedName) return;
    const symbols = symbolsText
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);

    setCreating(true);
    setCreateError(null);
    try {
      const wl = await createWatchlist(trimmedName, symbols);
      onCreated(wl);
      setName("");
      setSymbolsText("");
      setOpen(false);
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="text-sm bg-[#1D9E75] text-white font-medium px-4 py-2 rounded hover:bg-[#178a63] transition-colors"
      >
        + New Watchlist
      </button>
    );
  }

  return (
    <div className="bg-white border border-[#e4e4e8] rounded-lg p-5 mb-4">
      <h3 className="font-semibold text-gray-900 mb-4">New Watchlist</h3>

      <div className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Momentum Picks"
            className="w-full border border-[#e4e4e8] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#1D9E75] bg-white"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Symbols (comma-separated)
          </label>
          <textarea
            value={symbolsText}
            onChange={(e) => setSymbolsText(e.target.value)}
            placeholder="e.g. RELIANCE, TCS, INFY"
            rows={3}
            className="w-full border border-[#e4e4e8] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#1D9E75] bg-white resize-none"
          />
        </div>

        {createError != null && (
          <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded px-2 py-1">
            {createError}
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={handleCreate}
            disabled={creating || !name.trim()}
            className="bg-[#1D9E75] text-white text-sm font-medium px-4 py-2 rounded hover:bg-[#178a63] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {creating ? "Creating..." : "Create"}
          </button>
          <button
            onClick={() => {
              setOpen(false);
              setName("");
              setSymbolsText("");
              setCreateError(null);
            }}
            className="border border-[#e4e4e8] text-gray-600 text-sm font-medium px-4 py-2 rounded hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// --- Main page ---

export default function WatchlistsPage() {
  const [watchlists, setWatchlists] = useState<WatchlistItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadWatchlists() {
    setLoading(true);
    setError(null);
    try {
      const resp = await getWatchlists();
      setWatchlists(resp.watchlists);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load watchlists");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadWatchlists();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSync(id: string): Promise<void> {
    await syncWatchlistToTv(id);
    // Update tv_synced in local state on success
    setWatchlists((prev) =>
      prev == null
        ? prev
        : prev.map((wl) =>
            wl.id === id ? { ...wl, tv_synced: true } : wl
          )
    );
  }

  async function handleDelete(id: string): Promise<void> {
    await deleteWatchlist(id);
    setWatchlists((prev) =>
      prev == null ? prev : prev.filter((wl) => wl.id !== id)
    );
  }

  function handleCreated(wl: WatchlistItem) {
    setWatchlists((prev) => (prev == null ? [wl] : [wl, ...prev]));
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
              <span className="text-gray-800 font-medium">Watchlists</span>
            </nav>
          </div>
          <div className="text-xs text-gray-400">
            Jhaveri Intelligence Platform
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-4 py-6">
        {/* Page title + action */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <h1 className="text-lg font-semibold text-gray-900">Watchlists</h1>
            <p className="text-sm text-gray-500 mt-1">
              Manage symbol watchlists and sync them to TradingView.
            </p>
          </div>
        </div>

        {/* New watchlist form */}
        <div className="mb-4">
          <NewWatchlistForm onCreated={handleCreated} />
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
              onClick={loadWatchlists}
              className="ml-3 text-red-600 underline hover:no-underline"
            >
              Retry
            </button>
          </div>
        )}

        {!loading && error == null && watchlists != null && watchlists.length === 0 && (
          <div className="bg-gray-50 border border-[#e4e4e8] rounded-lg p-8 text-center text-sm text-gray-500">
            No watchlists yet. Create one above.
          </div>
        )}

        {!loading && error == null && watchlists != null && watchlists.length > 0 && (
          <div className="space-y-4" data-testid="watchlist-list">
            <div className="text-xs text-gray-400 mb-2">
              {watchlists.length} watchlist
              {watchlists.length !== 1 ? "s" : ""}
            </div>
            {watchlists.map((wl) => (
              <WatchlistCard
                key={wl.id}
                watchlist={wl}
                onSync={handleSync}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
