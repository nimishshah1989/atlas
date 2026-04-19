"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  {
    label: "Pulse",
    href: "/pulse",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
        <path d="M3 12h4l3-9 4 18 3-9h4" />
      </svg>
    ),
  },
  {
    label: "Explorer",
    href: "/explore/country",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
        <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
      </svg>
    ),
  },
  {
    label: "Breadth",
    href: "/breadth",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
        <rect x="3" y="3" width="7" height="9" /><rect x="14" y="3" width="7" height="5" />
        <rect x="14" y="12" width="7" height="9" /><rect x="3" y="16" width="7" height="5" />
      </svg>
    ),
  },
  {
    label: "Stocks",
    href: "/stocks/HDFCBANK",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
        <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
        <polyline points="16 7 22 7 22 13" />
      </svg>
    ),
  },
  {
    label: "Funds",
    href: "/funds/rank",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
        <path d="M2 20h20M6 20V10l6-8 6 8v10" />
      </svg>
    ),
  },
] as const;

function isActive(pathname: string, href: string): boolean {
  if (href === "/stocks/HDFCBANK") return pathname.startsWith("/stocks/");
  if (href === "/funds/rank") return pathname.startsWith("/funds/");
  if (href === "/explore/country") return pathname.startsWith("/explore/");
  return pathname === href || pathname.startsWith(href + "/");
}

export default function TopNav() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = React.useState(false);
  const [search, setSearch] = React.useState("");

  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 40,
        background: "var(--bg-surface)",
        borderBottom: "1px solid var(--border-default)",
        display: "flex",
        alignItems: "stretch",
        height: 52,
        padding: "0 var(--space-6)",
        gap: "var(--space-4)",
      }}
    >
      {/* Wordmark */}
      <Link
        href="/pulse"
        style={{
          fontFamily: "var(--font-sans)",
          fontSize: 15,
          fontWeight: 700,
          letterSpacing: "-0.02em",
          color: "var(--text-primary)",
          display: "flex",
          alignItems: "center",
          marginRight: "var(--space-2)",
          flexShrink: 0,
          textDecoration: "none",
        }}
      >
        atlas<strong style={{ fontWeight: 600, color: "var(--accent-700)" }}>.</strong>
      </Link>

      {/* Desktop nav links */}
      <nav
        style={{ display: "flex", alignItems: "stretch", flex: 1, gap: 0 }}
        aria-label="Main navigation"
      >
        {NAV_ITEMS.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: 13,
                fontWeight: active ? 600 : 500,
                color: active ? "var(--accent-700)" : "var(--text-secondary)",
                padding: "0 14px",
                borderBottom: active ? "2px solid var(--accent-700)" : "2px solid transparent",
                marginBottom: -1,
                textDecoration: "none",
                transition: "color 100ms, background 100ms",
                whiteSpace: "nowrap",
              }}
              onMouseEnter={(e) => {
                if (!active) {
                  (e.currentTarget as HTMLElement).style.color = "var(--text-primary)";
                  (e.currentTarget as HTMLElement).style.background = "var(--bg-hover)";
                }
              }}
              onMouseLeave={(e) => {
                if (!active) {
                  (e.currentTarget as HTMLElement).style.color = "var(--text-secondary)";
                  (e.currentTarget as HTMLElement).style.background = "transparent";
                }
              }}
            >
              <span style={{ width: 14, height: 14, display: "flex", flexShrink: 0 }}>
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Search */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          background: "var(--bg-inset)",
          border: "1px solid var(--border-default)",
          borderRadius: "var(--radius-sm)",
          padding: "0 10px",
          height: 30,
          alignSelf: "center",
          minWidth: 160,
        }}
      >
        <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" strokeWidth={2}>
          <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
        </svg>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search…"
          style={{
            border: "none",
            background: "transparent",
            fontSize: 12,
            color: "var(--text-primary)",
            outline: "none",
            width: "100%",
          }}
        />
      </div>

      {/* Live badge + avatar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-3)",
          fontSize: 10,
          color: "var(--text-tertiary)",
          flexShrink: 0,
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--rag-green-500)", display: "inline-block" }} />
          LIVE
        </span>
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: "var(--radius-full)",
            background: "var(--accent-700)",
            color: "var(--text-inverse)",
            fontSize: 11,
            fontWeight: 700,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          N
        </div>
      </div>

      {/* Mobile hamburger */}
      <button
        aria-label="Toggle navigation"
        aria-expanded={menuOpen}
        onClick={() => setMenuOpen((p) => !p)}
        style={{
          display: "none",
          marginLeft: "auto",
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: "0.5rem",
          color: "var(--text-primary)",
          alignSelf: "center",
        }}
      >
        <svg width={20} height={20} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
          {menuOpen ? (
            <><line x1={4} y1={4} x2={16} y2={16} /><line x1={16} y1={4} x2={4} y2={16} /></>
          ) : (
            <><line x1={2} y1={6} x2={18} y2={6} /><line x1={2} y1={10} x2={18} y2={10} /><line x1={2} y1={14} x2={18} y2={14} /></>
          )}
        </svg>
      </button>
    </header>
  );
}
