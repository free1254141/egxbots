import React from "react";

interface FlagProps {
  className?: string;
}

/** Crisp inline SVG flag of Egypt (EGX) with rounded corners and subtle border. */
export function EgyptFlag({ className = "w-5 h-3.5" }: FlagProps) {
  return (
    <svg
      viewBox="0 0 36 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      className={`inline-block shrink-0 rounded-[3px] border border-black/20 dark:border-white/25 shadow-xs ${className}`}
    >
      <rect width="36" height="8" y="0" fill="#CE1126" />
      <rect width="36" height="8" y="8" fill="#FFFFFF" />
      <rect width="36" height="8" y="16" fill="#000000" />
      {/* Eagle of Saladin emblem */}
      <g transform="translate(18, 12)">
        <path
          d="M-2.2 -2.6 L0 -3.2 L2.2 -2.6 L1.6 1.6 L0 2.7 L-1.6 1.6 Z"
          fill="#C09300"
        />
        <path
          d="M-3.1 -1.3 L-1.6 -1.9 L-1.3 0.9 L-2.6 0.4 Z M3.1 -1.3 L1.6 -1.9 L1.3 0.9 L2.6 0.4 Z"
          fill="#C09300"
        />
        <rect x="-0.55" y="-1.3" width="1.1" height="2.4" rx="0.3" fill="#FFFDF5" />
      </g>
    </svg>
  );
}

/** Crisp inline SVG flag of Saudi Arabia (TASI) with rounded corners and subtle border. */
export function SaudiFlag({ className = "w-5 h-3.5" }: FlagProps) {
  return (
    <svg
      viewBox="0 0 36 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      className={`inline-block shrink-0 rounded-[3px] border border-black/20 dark:border-white/25 shadow-xs ${className}`}
    >
      <rect width="36" height="24" fill="#006C35" />
      {/* Stylized Shahada calligraphy motif */}
      <g fill="#FFFFFF">
        <rect x="8" y="6.5" width="20" height="1.6" rx="0.8" />
        <rect x="10" y="9.4" width="16" height="1.5" rx="0.75" />
        <rect x="12" y="6.0" width="1.4" height="4.8" rx="0.7" />
        <rect x="17.5" y="5.6" width="1.4" height="5.2" rx="0.7" />
        <rect x="23" y="6.0" width="1.4" height="4.8" rx="0.7" />
      </g>
      {/* Horizontal Arab sword */}
      <path
        d="M8.5 15.8 H25.2 L27.5 14.9 L25.2 17.0 H8.5 Z"
        fill="#FFFFFF"
      />
      <rect x="24.2" y="13.9" width="1.3" height="3.9" rx="0.5" fill="#FFFFFF" />
      <circle cx="27.2" cy="15.9" r="0.9" fill="#FFFFFF" />
    </svg>
  );
}
