"use client";

import { useEffect, useState } from "react";

export function SplashScreen() {
  const [visible, setVisible] = useState(true);
  const [fading, setFading] = useState(false);

  useEffect(() => {
    const fadeTimer = setTimeout(() => setFading(true), 2200);
    const hideTimer = setTimeout(() => setVisible(false), 2800);
    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(hideTimer);
    };
  }, []);

  if (!visible) return null;

  return (
    <div
      className="splash-root"
      style={{ opacity: fading ? 0 : 1 }}
      aria-hidden="true"
    >
      {/* Subtle grid texture */}
      <div className="splash-grid" />

      {/* Animated scan line */}
      <div className="splash-scanline" />

      {/* Center content */}
      <div className="splash-center">
        {/* Logo mark — satellite dish / detection icon */}
        <div className="splash-logo-wrap">
          <svg
            className="splash-logo"
            viewBox="0 0 64 64"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            {/* Outer ring */}
            <circle
              cx="32"
              cy="32"
              r="28"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeDasharray="6 4"
              className="splash-ring-outer"
            />
            {/* Inner ring */}
            <circle
              cx="32"
              cy="32"
              r="18"
              stroke="currentColor"
              strokeWidth="1"
              opacity="0.4"
            />
            {/* Cross-hair lines */}
            <line x1="32" y1="4" x2="32" y2="14" stroke="currentColor" strokeWidth="1.5" />
            <line x1="32" y1="50" x2="32" y2="60" stroke="currentColor" strokeWidth="1.5" />
            <line x1="4" y1="32" x2="14" y2="32" stroke="currentColor" strokeWidth="1.5" />
            <line x1="50" y1="32" x2="60" y2="32" stroke="currentColor" strokeWidth="1.5" />
            {/* Center dot */}
            <circle cx="32" cy="32" r="3.5" fill="currentColor" />
            {/* Pulse dot */}
            <circle cx="32" cy="32" r="8" stroke="currentColor" strokeWidth="1" className="splash-pulse" />
          </svg>

          {/* Rotating radar sweep */}
          <div className="splash-radar" />
        </div>

        {/* Wordmark */}
        <div className="splash-wordmark">
          <span className="splash-title">IMBONESHA</span>
          <span className="splash-sub">Construction Intelligence Platform</span>
        </div>

        {/* Loading bar */}
        <div className="splash-bar-track">
          <div className="splash-bar-fill" />
        </div>

        {/* Status text */}
        <span className="splash-status">Initialising detection systems…</span>
      </div>

      {/* Corner accents */}
      <div className="splash-corner splash-corner-tl" />
      <div className="splash-corner splash-corner-tr" />
      <div className="splash-corner splash-corner-bl" />
      <div className="splash-corner splash-corner-br" />

      <style>{`
        .splash-root {
          position: fixed;
          inset: 0;
          z-index: 9999;
          background: var(--background);
          display: flex;
          align-items: center;
          justify-content: center;
          transition: opacity 0.6s cubic-bezier(0.4, 0, 0.2, 1);
        }

        /* Dot-grid background */
        .splash-grid {
          position: absolute;
          inset: 0;
          background-image: radial-gradient(circle, color-mix(in oklch, var(--primary) 12%, transparent) 1px, transparent 1px);
          background-size: 28px 28px;
          pointer-events: none;
        }

        /* Horizontal scan line that sweeps top→bottom */
        .splash-scanline {
          position: absolute;
          left: 0;
          right: 0;
          height: 1px;
          background: linear-gradient(90deg, transparent, color-mix(in oklch, var(--primary) 50%, transparent), transparent);
          animation: scanline 2s linear infinite;
          pointer-events: none;
        }
        @keyframes scanline {
          0%   { top: 0%; opacity: 0; }
          5%   { opacity: 1; }
          95%  { opacity: 1; }
          100% { top: 100%; opacity: 0; }
        }

        .splash-center {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 20px;
          animation: fadeUp 0.7s cubic-bezier(0.16, 1, 0.3, 1) both;
        }
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(16px); }
          to   { opacity: 1; transform: translateY(0); }
        }

        /* Logo container */
        .splash-logo-wrap {
          position: relative;
          width: 96px;
          height: 96px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .splash-logo {
          width: 72px;
          height: 72px;
          color: var(--primary);
          position: relative;
          z-index: 1;
        }

        /* Rotating outer ring */
        .splash-ring-outer {
          animation: spin 8s linear infinite;
          transform-origin: 32px 32px;
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        /* Pulse ring */
        .splash-pulse {
          transform-origin: 32px 32px;
          animation: pulse 1.8s ease-out infinite;
        }
        @keyframes pulse {
          0%   { r: 8; opacity: 0.8; }
          100% { r: 20; opacity: 0; }
        }

        /* Radar sweep overlay */
        .splash-radar {
          position: absolute;
          inset: 0;
          border-radius: 50%;
          background: conic-gradient(
            from 0deg,
            transparent 0deg,
            color-mix(in oklch, var(--primary) 22%, transparent) 40deg,
            transparent 90deg
          );
          animation: sweep 2s linear infinite;
        }
        @keyframes sweep {
          to { transform: rotate(360deg); }
        }

        /* Wordmark */
        .splash-wordmark {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 4px;
        }
        .splash-title {
          font-family: var(--font-geist-sans), ui-sans-serif, system-ui, sans-serif;
          font-size: 1.75rem;
          font-weight: 700;
          letter-spacing: 0.22em;
          color: var(--foreground);
        }
        .splash-sub {
          font-family: var(--font-geist-mono), ui-monospace, monospace;
          font-size: 0.65rem;
          letter-spacing: 0.18em;
          color: var(--primary);
          text-transform: uppercase;
          opacity: 0.75;
        }

        /* Loading bar */
        .splash-bar-track {
          width: 180px;
          height: 2px;
          background: color-mix(in oklch, var(--primary) 15%, transparent);
          border-radius: 999px;
          overflow: hidden;
        }
        .splash-bar-fill {
          height: 100%;
          background: linear-gradient(90deg, var(--primary), color-mix(in oklch, var(--primary) 70%, white));
          border-radius: 999px;
          animation: load 2s cubic-bezier(0.4, 0, 0.2, 1) forwards;
        }
        @keyframes load {
          0%   { width: 0%; }
          40%  { width: 55%; }
          70%  { width: 78%; }
          100% { width: 100%; }
        }

        /* Status text */
        .splash-status {
          font-family: var(--font-geist-mono), ui-monospace, monospace;
          font-size: 0.6rem;
          letter-spacing: 0.12em;
          color: color-mix(in oklch, var(--primary) 60%, transparent);
          text-transform: uppercase;
          animation: blink 1.2s step-start infinite;
        }
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.3; }
        }

        /* Corner accents */
        .splash-corner {
          position: absolute;
          width: 20px;
          height: 20px;
          border-color: color-mix(in oklch, var(--primary) 35%, transparent);
          border-style: solid;
        }
        .splash-corner-tl { top: 24px; left: 24px;  border-width: 1px 0 0 1px; }
        .splash-corner-tr { top: 24px; right: 24px; border-width: 1px 1px 0 0; }
        .splash-corner-bl { bottom: 24px; left: 24px;  border-width: 0 0 1px 1px; }
        .splash-corner-br { bottom: 24px; right: 24px; border-width: 0 1px 1px 0; }
      `}</style>
    </div>
  );
}
