"use client";

import { useState } from "react";
import { type SimulationConfig, type SimulationParameters, type SignalType, type SimulationRunResponse, runSimulation } from "@/lib/api-simulate";

const SIGNALS: { value: SignalType; label: string }[] = [
  { value: "breadth", label: "Breadth" },
  { value: "mcclellan", label: "McClellan Oscillator" },
  { value: "rs", label: "Relative Strength (RS)" },
  { value: "pe", label: "P/E Ratio" },
  { value: "regime", label: "Market Regime" },
  { value: "sector_rs", label: "Sector RS" },
  { value: "mcclellan_summation", label: "McClellan Summation" },
  { value: "combined", label: "Combined (AND/OR)" },
];

const INST_TYPES = [
  { value: "equity", label: "Equity (Stock)" },
  { value: "mf", label: "Mutual Fund" },
  { value: "etf", label: "ETF" },
];

const DEF: SimulationParameters = { sip_amount: "10000", lumpsum_amount: "50000", buy_level: "60", sell_level: "40", reentry_level: null, sell_pct: "100", redeploy_pct: "100", cooldown_days: 30 };

function StepDot({ n, cur, label }: { n: number; cur: number; label: string }) {
  const done = n < cur;
  const active = n === cur;
  return (
    <div className="flex items-center gap-2">
      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold border ${done ? "bg-[#1a9a6c] border-[#1a9a6c] text-white" : active ? "bg-white border-[#0d8a7a] text-[#0d8a7a]" : "bg-white border-gray-300 text-gray-400"}`}>{done ? "✓" : n}</div>
      <span className={`text-xs font-medium ${active ? "text-[#0d8a7a]" : done ? "text-gray-600" : "text-gray-400"}`}>{label}</span>
    </div>
  );
}

const FL = "block text-xs font-medium text-gray-600 mb-1";
const INPUT = "w-full border border-[#e4e4e8] rounded px-2 py-1.5 text-sm focus:outline-none focus:border-[#0d8a7a] bg-white";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><label className={FL}>{label}</label>{children}</div>;
}

function Sel({ value, onChange, opts }: { value: string; onChange: (v: string) => void; opts: { value: string; label: string }[] }) {
  return <select value={value} onChange={e => onChange(e.target.value)} className={INPUT}>{opts.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>;
}

function Inp({ value, onChange, placeholder, type = "text" }: { value: string; onChange: (v: string) => void; placeholder?: string; type?: string }) {
  return <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} className={INPUT} />;
}

function RR({ label, value }: { label: string; value: string }) {
  return <><span className="text-gray-500">{label}</span><span className="font-medium text-[#1a1a2e]">{value}</span></>;
}

interface Props { onResult: (r: SimulationRunResponse, c: SimulationConfig) => void; initialConfig?: SimulationConfig | null }

export default function SimulationBuilder({ onResult, initialConfig }: Props) {
  const [step, setStep] = useState(1);
  const [instrument, setInstrument] = useState(initialConfig?.instrument ?? "");
  const [instrType, setInstrType] = useState(initialConfig?.instrument_type ?? "equity");
  const [signal, setSignal] = useState<SignalType>(initialConfig?.signal ?? "breadth");
  const [params, setParams] = useState<SimulationParameters>(initialConfig?.parameters ?? { ...DEF });
  const [startDate, setStartDate] = useState(initialConfig?.start_date ?? "2018-01-01");
  const [endDate, setEndDate] = useState(initialConfig?.end_date ?? "2024-12-31");
  const [sigA, setSigA] = useState<SignalType>(initialConfig?.combined_config?.signal_a ?? "breadth");
  const [sigB, setSigB] = useState<SignalType>(initialConfig?.combined_config?.signal_b ?? "mcclellan");
  const [logic, setLogic] = useState<"AND" | "OR">(initialConfig?.combined_config?.logic ?? "AND");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buildConfig = (): SimulationConfig => ({
    signal, instrument, instrument_type: instrType, parameters: params, start_date: startDate, end_date: endDate,
    combined_config: signal === "combined" ? { signal_a: sigA, signal_b: sigB, logic } : null,
  });

  const handleRun = async () => {
    setLoading(true); setError(null);
    try { const r = await runSimulation(buildConfig()); onResult(r, buildConfig()); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  };

  const nonCombinedSigs = SIGNALS.filter(o => o.value !== "combined");

  return (
    <div className="bg-white border border-[#e4e4e8] rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b bg-[#f9f9f7] flex items-center gap-4">
        <StepDot n={1} cur={step} label="Instrument" />
        <div className="flex-1 border-t border-gray-200" />
        <StepDot n={2} cur={step} label="Parameters" />
        <div className="flex-1 border-t border-gray-200" />
        <StepDot n={3} cur={step} label="Review & Run" />
      </div>

      <div className="p-4">
        {step === 1 && (
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-[#1a1a2e]">Step 1 — Choose Instrument and Signal</h3>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Instrument Type"><Sel value={instrType} onChange={setInstrType} opts={INST_TYPES} /></Field>
              <Field label={instrType === "mf" ? "Morningstar ID" : "Symbol (e.g. RELIANCE.NS)"}><Inp value={instrument} onChange={setInstrument} placeholder={instrType === "mf" ? "F12345678" : "RELIANCE.NS"} /></Field>
              <Field label="Signal Type"><Sel value={signal} onChange={v => setSignal(v as SignalType)} opts={SIGNALS} /></Field>
              {signal === "combined" && (
                <>
                  <Field label="Signal A"><Sel value={sigA} onChange={v => setSigA(v as SignalType)} opts={nonCombinedSigs} /></Field>
                  <Field label="Signal B"><Sel value={sigB} onChange={v => setSigB(v as SignalType)} opts={nonCombinedSigs} /></Field>
                  <Field label="Combine Logic"><Sel value={logic} onChange={v => setLogic(v as "AND" | "OR")} opts={[{ value: "AND", label: "AND (both required)" }, { value: "OR", label: "OR (either)" }]} /></Field>
                </>
              )}
            </div>
            <div className="flex justify-end">
              <button disabled={!instrument.trim()} onClick={() => setStep(2)} className="px-4 py-1.5 text-sm font-medium bg-[#0d8a7a] text-white rounded disabled:opacity-40 hover:bg-[#0b7a6c]">Next</button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-[#1a1a2e]">Step 2 — Set Parameters</h3>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Monthly SIP Amount (INR)"><Inp type="number" value={params.sip_amount} onChange={v => setParams(p => ({ ...p, sip_amount: v }))} placeholder="10000" /></Field>
              <Field label="Lumpsum Deployment (INR)"><Inp type="number" value={params.lumpsum_amount} onChange={v => setParams(p => ({ ...p, lumpsum_amount: v }))} placeholder="50000" /></Field>
              <Field label="Buy Level (signal threshold)"><Inp type="number" value={params.buy_level} onChange={v => setParams(p => ({ ...p, buy_level: v }))} placeholder="60" /></Field>
              <Field label="Sell Level (signal threshold)"><Inp type="number" value={params.sell_level} onChange={v => setParams(p => ({ ...p, sell_level: v }))} placeholder="40" /></Field>
              <Field label="Re-entry Level (optional)"><Inp type="number" value={params.reentry_level ?? ""} onChange={v => setParams(p => ({ ...p, reentry_level: v || null }))} placeholder="50" /></Field>
              <Field label="Sell Percentage (%)"><Inp type="number" value={params.sell_pct} onChange={v => setParams(p => ({ ...p, sell_pct: v }))} placeholder="100" /></Field>
              <Field label="Redeploy Percentage (%)"><Inp type="number" value={params.redeploy_pct} onChange={v => setParams(p => ({ ...p, redeploy_pct: v }))} placeholder="100" /></Field>
              <Field label="Cooldown Days"><Inp type="number" value={String(params.cooldown_days)} onChange={v => setParams(p => ({ ...p, cooldown_days: parseInt(v, 10) || 30 }))} placeholder="30" /></Field>
              <Field label="Start Date"><Inp type="date" value={startDate} onChange={setStartDate} /></Field>
              <Field label="End Date"><Inp type="date" value={endDate} onChange={setEndDate} /></Field>
            </div>
            <div className="flex justify-between">
              <button onClick={() => setStep(1)} className="px-4 py-1.5 text-sm font-medium border border-gray-300 text-gray-600 rounded hover:bg-gray-50">Back</button>
              <button disabled={!params.buy_level || !params.sell_level || !startDate || !endDate} onClick={() => setStep(3)} className="px-4 py-1.5 text-sm font-medium bg-[#0d8a7a] text-white rounded disabled:opacity-40 hover:bg-[#0b7a6c]">Review</button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-[#1a1a2e]">Step 3 — Review and Run</h3>
            <div className="bg-[#f9f9f7] border border-[#e4e4e8] rounded p-3 text-sm">
              <div className="grid grid-cols-2 gap-x-6 gap-y-1">
                <RR label="Instrument" value={instrument} />
                <RR label="Type" value={instrType} />
                <RR label="Signal" value={SIGNALS.find(o => o.value === signal)?.label ?? signal} />
                {signal === "combined" && <RR label="Combined" value={`${sigA} ${logic} ${sigB}`} />}
                <RR label="Date Range" value={`${startDate} — ${endDate}`} />
                <RR label="SIP Amount" value={`₹${params.sip_amount}`} />
                <RR label="Lumpsum" value={`₹${params.lumpsum_amount}`} />
                <RR label="Buy / Sell Level" value={`${params.buy_level} / ${params.sell_level}`} />
                <RR label="Sell / Redeploy %" value={`${params.sell_pct}% / ${params.redeploy_pct}%`} />
                <RR label="Cooldown" value={`${params.cooldown_days} days`} />
              </div>
            </div>
            {error && <div className="border border-red-200 bg-red-50 rounded p-3 text-sm text-red-700">{error}</div>}
            <div className="flex justify-between">
              <button onClick={() => setStep(2)} disabled={loading} className="px-4 py-1.5 text-sm font-medium border border-gray-300 text-gray-600 rounded hover:bg-gray-50 disabled:opacity-40">Back</button>
              <button onClick={handleRun} disabled={loading} className="px-6 py-1.5 text-sm font-semibold bg-[#0d8a7a] text-white rounded hover:bg-[#0b7a6c] disabled:opacity-60 flex items-center gap-2">
                {loading ? <><span className="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />Running simulation...</> : "Run Simulation"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
