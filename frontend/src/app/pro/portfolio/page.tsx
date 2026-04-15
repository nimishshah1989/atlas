"use client";

import { useState, useEffect, useRef } from "react";
import {
  listPortfolios,
  importCamsPdf,
  type PortfolioResponse,
} from "@/lib/api-portfolio";
import { formatCurrency } from "@/lib/format";

function PortfolioCard({ p }: { p: PortfolioResponse }) {
  const totalValue = p.holdings.reduce((sum, h) => {
    const v = parseFloat(h.current_value ?? "0");
    return sum + (isNaN(v) ? 0 : v);
  }, 0);

  const typeLabel: Record<string, string> = {
    cams_import: "CAMS Import",
    manual: "Manual",
    model: "Model",
  };

  const ownerLabel: Record<string, string> = {
    pms: "PMS",
    ria_client: "RIA Client",
    retail: "Retail",
  };

  return (
    <a
      href={`/pro/portfolio/${p.id}`}
      className="block bg-white border border-[#e4e4e8] rounded-lg p-5 hover:border-[#1D9E75] hover:shadow-sm transition-all"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="font-semibold text-gray-900 truncate">
            {p.name ?? "Unnamed Portfolio"}
          </h3>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
              {typeLabel[p.portfolio_type] ?? p.portfolio_type}
            </span>
            <span className="text-xs text-gray-400">
              {ownerLabel[p.owner_type] ?? p.owner_type}
            </span>
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-sm font-semibold text-gray-900">
            {totalValue > 0 ? formatCurrency(totalValue) : "—"}
          </div>
          <div className="text-xs text-gray-400 mt-0.5">
            {p.holdings.length} holding{p.holdings.length !== 1 ? "s" : ""}
          </div>
        </div>
      </div>
      <div className="text-xs text-gray-400 mt-3">
        Created{" "}
        {new Date(p.created_at).toLocaleDateString("en-IN", {
          day: "2-digit",
          month: "short",
          year: "numeric",
        })}
      </div>
    </a>
  );
}

export default function PortfolioListPage() {
  const [portfolios, setPortfolios] = useState<PortfolioResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Import CAMS state
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importSuccess, setImportSuccess] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [portfolioName, setPortfolioName] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadPortfolios();
  }, []);

  async function loadPortfolios() {
    setLoading(true);
    setError(null);
    try {
      const resp = await listPortfolios();
      setPortfolios(resp.portfolios);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load portfolios");
    } finally {
      setLoading(false);
    }
  }

  async function handleImport() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;

    setImporting(true);
    setImportError(null);
    setImportSuccess(null);

    try {
      const result = await importCamsPdf(
        file,
        password || undefined,
        portfolioName || undefined
      );
      setImportSuccess(
        `Imported "${result.portfolio_name ?? "portfolio"}" — ${result.mapped_count} mapped, ${result.pending_count} pending review`
      );
      setPassword("");
      setPortfolioName("");
      if (fileRef.current) fileRef.current.value = "";
      await loadPortfolios();
    } catch (e) {
      setImportError(
        e instanceof Error ? e.message : "Import failed"
      );
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b bg-white sticky top-0 z-10">
        <div className="max-w-[1600px] mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a href="/" className="text-xl font-bold tracking-tight">
              <span className="text-[#1D9E75]">ATLAS</span>
              <span className="text-gray-400 text-sm font-normal ml-2">Pro</span>
            </a>
            <nav className="flex items-center gap-1 text-sm text-gray-500 ml-2">
              <a href="/" className="hover:text-gray-800">Home</a>
              <span>/</span>
              <span className="text-gray-800 font-medium">Portfolios</span>
            </nav>
          </div>
          <div className="text-xs text-gray-400">Jhaveri Intelligence Platform</div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold text-gray-900">My Portfolios</h2>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Portfolio list */}
          <div className="lg:col-span-2 space-y-4">
            {loading && (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-24 bg-gray-100 rounded-lg animate-pulse"
                  />
                ))}
              </div>
            )}

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
                {error}
                <button
                  onClick={loadPortfolios}
                  className="ml-3 text-red-600 underline hover:no-underline"
                >
                  Retry
                </button>
              </div>
            )}

            {!loading && !error && portfolios.length === 0 && (
              <div className="bg-gray-50 border border-[#e4e4e8] rounded-lg p-8 text-center text-sm text-gray-500">
                No portfolios yet. Import a CAMS PDF to get started.
              </div>
            )}

            {!loading &&
              portfolios.map((p) => <PortfolioCard key={p.id} p={p} />)}
          </div>

          {/* Right: Import panel */}
          <div className="lg:col-span-1">
            <div className="bg-white border border-[#e4e4e8] rounded-lg p-5 sticky top-20">
              <h3 className="font-semibold text-gray-900 mb-4 text-sm">
                Import CAMS Statement
              </h3>

              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    CAS PDF File
                  </label>
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".pdf"
                    className="block w-full text-xs text-gray-600 file:mr-2 file:py-1 file:px-2 file:rounded file:border file:border-[#e4e4e8] file:text-xs file:font-medium file:bg-gray-50 file:text-gray-700 hover:file:bg-gray-100"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    PDF Password (optional)
                  </label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Leave blank if no password"
                    className="w-full border border-[#e4e4e8] rounded px-2 py-1.5 text-sm focus:outline-none focus:border-[#1D9E75] bg-white"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Portfolio Name (optional)
                  </label>
                  <input
                    type="text"
                    value={portfolioName}
                    onChange={(e) => setPortfolioName(e.target.value)}
                    placeholder="e.g. My CAMS Portfolio"
                    className="w-full border border-[#e4e4e8] rounded px-2 py-1.5 text-sm focus:outline-none focus:border-[#1D9E75] bg-white"
                  />
                </div>

                <button
                  onClick={handleImport}
                  disabled={importing}
                  className="w-full bg-[#1D9E75] text-white text-sm font-medium py-2 rounded hover:bg-[#178a63] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {importing ? "Importing..." : "Import PDF"}
                </button>

                {importError && (
                  <div className="bg-red-50 border border-red-200 rounded p-3 text-xs text-red-700">
                    {importError}
                  </div>
                )}

                {importSuccess && (
                  <div className="bg-emerald-50 border border-emerald-200 rounded p-3 text-xs text-emerald-700">
                    {importSuccess}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
