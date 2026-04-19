"use client";

import React from "react";
import type { RankFilters } from "@/app/funds/rank/page";

interface FilterRailProps {
  filters: RankFilters;
  onFiltersChange: (f: RankFilters) => void;
}

const CATEGORIES = [
  { value: null, label: "All categories" },
  { value: "Flexi Cap", label: "Flexi Cap" },
  { value: "Large Cap", label: "Large Cap" },
  { value: "Mid Cap", label: "Mid Cap" },
  { value: "Small Cap", label: "Small Cap" },
  { value: "ELSS", label: "ELSS" },
  { value: "Multi Cap", label: "Multi Cap" },
];

const AUM_OPTIONS = [
  { value: null, label: "All AUM" },
  { value: "large", label: "Above ₹25,000 Cr" },
  { value: "mid", label: "₹10,000–25,000 Cr" },
  { value: "small", label: "Below ₹10,000 Cr" },
];

const PERIOD_OPTIONS = [
  { value: null, label: "All periods" },
  { value: "1y", label: "1 Year" },
  { value: "3y", label: "3 Years" },
  { value: "5y", label: "5 Years" },
];

export default function FilterRail({ filters, onFiltersChange }: FilterRailProps) {
  const setCategory = (v: string | null) =>
    onFiltersChange({ ...filters, category: v });
  const setAmc = (v: string | null) =>
    onFiltersChange({ ...filters, amc: v });
  const setPeriod = (v: string | null) =>
    onFiltersChange({ ...filters, period: v });

  return (
    <aside data-block="filter-rail" className="flex flex-col gap-3">
      {/* Category filter */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <fieldset>
          <legend className="w-full px-3 py-2 bg-gray-50 border-b border-gray-100 text-xs font-bold uppercase tracking-widest text-gray-400">
            Category
          </legend>
          <div className="p-2 flex flex-col gap-0.5">
            {CATEGORIES.map((opt) => {
              const isActive = filters.category === opt.value;
              return (
                <label
                  key={String(opt.value)}
                  className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer text-xs transition-colors ${
                    isActive
                      ? "bg-teal-50 text-teal-700 font-semibold"
                      : "text-gray-500 hover:bg-gray-50 hover:text-gray-800"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={isActive}
                    onChange={() => setCategory(isActive ? null : opt.value)}
                    aria-label={opt.label}
                  />
                  <span
                    className={`w-2 h-2 rounded-full flex-shrink-0 ${
                      opt.value === null ? "bg-teal-600" :
                      opt.value === "Flexi Cap" ? "bg-blue-400" :
                      opt.value === "Large Cap" ? "bg-emerald-400" :
                      opt.value === "Mid Cap" ? "bg-amber-400" :
                      opt.value === "Small Cap" ? "bg-red-400" :
                      "bg-gray-400"
                    }`}
                  />
                  {opt.label}
                </label>
              );
            })}
          </div>
        </fieldset>
      </div>

      {/* AUM range filter */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <fieldset>
          <legend className="w-full px-3 py-2 bg-gray-50 border-b border-gray-100 text-xs font-bold uppercase tracking-widest text-gray-400">
            AUM Range
          </legend>
          <div className="p-2 flex flex-col gap-0.5">
            {AUM_OPTIONS.map((opt) => {
              const isActive = filters.amc === opt.value;
              return (
                <label
                  key={String(opt.value)}
                  className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer text-xs transition-colors ${
                    isActive
                      ? "bg-teal-50 text-teal-700 font-semibold"
                      : "text-gray-500 hover:bg-gray-50 hover:text-gray-800"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={isActive}
                    onChange={() => setAmc(isActive ? null : opt.value)}
                    aria-label={opt.label}
                  />
                  {opt.label}
                </label>
              );
            })}
          </div>
        </fieldset>
      </div>

      {/* Period filter */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <fieldset>
          <legend className="w-full px-3 py-2 bg-gray-50 border-b border-gray-100 text-xs font-bold uppercase tracking-widest text-gray-400">
            Time Period
          </legend>
          <div className="p-2 flex flex-col gap-0.5">
            {PERIOD_OPTIONS.map((opt) => {
              const isActive = filters.period === opt.value;
              return (
                <label
                  key={String(opt.value)}
                  className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer text-xs transition-colors ${
                    isActive
                      ? "bg-teal-50 text-teal-700 font-semibold"
                      : "text-gray-500 hover:bg-gray-50 hover:text-gray-800"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={isActive}
                    onChange={() => setPeriod(isActive ? null : opt.value)}
                    aria-label={opt.label}
                  />
                  {opt.label}
                </label>
              );
            })}
          </div>
        </fieldset>
      </div>
    </aside>
  );
}
