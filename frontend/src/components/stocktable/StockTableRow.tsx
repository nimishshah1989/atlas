"use client";

import type { StockSummary } from "@/lib/api";
import TvChip from "./TvChip";
import {
  formatCurrency,
  formatDecimal,
  quadrantBg,
  quadrantColor,
  signColor,
} from "@/lib/format";

function DmaDot({ above }: { above: boolean | null | undefined }) {
  if (above === true) return <span className="text-emerald-500">{"\u25cf"}</span>;
  if (above === false) return <span className="text-red-500">{"\u25cf"}</span>;
  return <>{"\u2014"}</>;
}

export default function StockTableRow({
  s,
  onSelect,
  tvScore,
}: {
  s: StockSummary;
  onSelect: (symbol: string) => void;
  tvScore?: number | null;
}) {
  return (
    <tr
      className="hover:bg-gray-50 cursor-pointer"
      onClick={() => onSelect(s.symbol)}
    >
      <td className="px-2 py-1.5 font-medium text-[#1D9E75] whitespace-nowrap">
        {s.symbol}
      </td>
      <td className="px-2 py-1.5 text-gray-700 max-w-[200px] truncate">
        {s.company_name}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {formatCurrency(s.close)}
      </td>
      <td
        className={`px-2 py-1.5 text-right tabular-nums font-medium ${signColor(s.rs_composite)}`}
      >
        {formatDecimal(s.rs_composite)}
      </td>
      <td
        className={`px-2 py-1.5 text-right tabular-nums ${signColor(s.rs_momentum)}`}
      >
        {formatDecimal(s.rs_momentum)}
      </td>
      <td className="px-2 py-1.5 text-center">
        <span
          className={`text-xs px-1.5 py-0.5 rounded border ${quadrantBg(s.quadrant)} ${quadrantColor(s.quadrant)}`}
        >
          {s.quadrant || "\u2014"}
        </span>
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {formatDecimal(s.rsi_14, 1)}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {formatDecimal(s.adx_14, 1)}
      </td>
      <td className="px-2 py-1.5 text-center">
        <DmaDot above={s.above_200dma} />
      </td>
      <td className="px-2 py-1.5 text-center">
        <DmaDot above={s.above_50dma} />
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {formatDecimal(s.beta_nifty)}
      </td>
      <td
        className={`px-2 py-1.5 text-right tabular-nums ${signColor(s.sharpe_1y)}`}
      >
        {formatDecimal(s.sharpe_1y)}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {s.mf_holder_count ?? "\u2014"}
      </td>
      <td className="px-2 py-1.5 text-center">
        <TvChip score={tvScore} size="sm" />
      </td>
      <td className="px-2 py-1.5 text-center text-xs text-gray-500">
        {s.cap_category || "\u2014"}
      </td>
    </tr>
  );
}
