export interface ChatWallpaper {
  id: string;
  name: string;
  nameEn: string;
  category: "doodle" | "pattern" | "solid" | "custom";
  previewBg: string;
  style: React.CSSProperties;
  className?: string;
}

// 1. Trading & Market Doodle SVG pattern
const TRADING_DOODLE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
  <!-- Candlestick -->
  <rect x="20" y="24" width="12" height="22" rx="2" />
  <line x1="26" y1="16" x2="26" y2="24" />
  <line x1="26" y1="46" x2="26" y2="54" />
  <!-- Trending Arrow -->
  <path d="M55 45 L72 28 L88 40 L108 20" />
  <path d="M100 20 H108 V28" />
  <!-- Coin / Dollar -->
  <circle cx="135" cy="30" r="12" />
  <path d="M135 24 V36 M131 28 C131 26 139 26 139 30 C139 34 131 32 131 36" />
  <!-- Bar Chart -->
  <rect x="18" y="85" width="8" height="20" rx="1" />
  <rect x="30" y="75" width="8" height="30" rx="1" />
  <rect x="42" y="92" width="8" height="13" rx="1" />
  <!-- Robot / AI -->
  <rect x="70" y="78" width="22" height="18" rx="4" />
  <circle cx="76" cy="87" r="2" fill="currentColor" />
  <circle cx="86" cy="87" r="2" fill="currentColor" />
  <line x1="81" y1="72" x2="81" y2="78" />
  <!-- Diamond -->
  <path d="M130 80 L142 68 L154 80 L142 96 Z" />
  <!-- Bull Horns / Trend -->
  <path d="M22 138 C28 126 38 124 45 130 C52 124 62 126 68 138" />
  <!-- Percent Symbol -->
  <circle cx="95" cy="128" r="3" />
  <circle cx="111" cy="144" r="3" />
  <line x1="113" y1="126" x2="93" y2="146" />
  <!-- Rocket -->
  <path d="M135 145 L145 125 L150 130 L140 150 Z" />
  <path d="M132 148 L128 152" />
</svg>`;

// 2. WhatsApp Classic Style Doodle SVG pattern
const WHATSAPP_DOODLE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
  <!-- Coffee Cup -->
  <path d="M20 32 H44 V46 C44 52 38 56 32 56 C26 56 20 52 20 46 Z" />
  <path d="M44 36 H48 C51 36 53 38 53 41 C53 44 51 46 48 46 H44" />
  <!-- Chat Bubble -->
  <path d="M75 22 C65 22 58 28 58 36 C58 41 62 45 67 48 L65 55 L73 50 C74 50 75 50 75 50 C85 50 92 44 92 36 C92 28 85 22 75 22 Z" />
  <!-- Star -->
  <path d="M130 20 L133 28 L141 29 L135 35 L137 43 L130 39 L123 43 L125 35 L119 29 L127 28 Z" />
  <!-- Heart -->
  <path d="M30 85 C25 80 16 84 16 91 C16 99 30 108 30 108 C30 108 44 99 44 91 C44 84 35 80 30 85 Z" />
  <!-- Sun -->
  <circle cx="85" cy="90" r="10" />
  <line x1="85" y1="74" x2="85" y2="77" />
  <line x1="85" y1="103" x2="85" y2="106" />
  <line x1="69" y1="90" x2="72" y2="90" />
  <line x1="98" y1="90" x2="101" y2="90" />
  <!-- Paper Plane -->
  <path d="M125 85 L150 75 L140 105 L133 93 L125 85 Z" />
  <path d="M150 75 L133 93" />
  <!-- Music Note -->
  <path d="M25 145 V130 H40 V145" />
  <circle cx="21" cy="145" r="4" fill="currentColor" />
  <circle cx="36" cy="145" r="4" fill="currentColor" />
  <!-- Cloud -->
  <path d="M70 145 C67 145 64 143 64 140 C64 137 66 135 69 135 C70 131 74 128 78 128 C82 128 85 130 86 133 C88 133 90 135 90 137 C90 141 87 145 83 145 Z" />
  <!-- Lightbulb -->
  <circle cx="135" cy="135" r="8" />
  <path d="M131 143 H139 M132 146 H138" />
</svg>`;

// 3. Candlesticks Matrix SVG pattern
const CANDLESTICKS_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100" fill="none" stroke="currentColor" stroke-width="1">
  <rect x="15" y="25" width="10" height="25" rx="1" fill="currentColor" fill-opacity="0.15" />
  <line x1="20" y1="15" x2="20" y2="25" />
  <line x1="20" y1="50" x2="20" y2="60" />
  
  <rect x="45" y="40" width="10" height="30" rx="1" />
  <line x1="50" y1="30" x2="50" y2="40" />
  <line x1="50" y1="70" x2="50" y2="80" />
  
  <rect x="75" y="20" width="10" height="20" rx="1" fill="currentColor" fill-opacity="0.15" />
  <line x1="80" y1="10" x2="80" y2="20" />
  <line x1="80" y1="40" x2="80" y2="52" />
</svg>`;

// 4. AI Cyber Circuit Pattern
const CIRCUIT_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120" fill="none" stroke="currentColor" stroke-width="1.2">
  <circle cx="20" cy="20" r="3" fill="currentColor" />
  <path d="M20 20 H50 L70 40 V70 L90 90 H110" />
  <circle cx="110" cy="90" r="3" fill="currentColor" />
  <circle cx="90" cy="30" r="3" fill="currentColor" />
  <path d="M90 30 V50 L70 70 H40 L20 90 V110" />
  <circle cx="20" cy="110" r="3" fill="currentColor" />
  <circle cx="60" cy="110" r="2" fill="currentColor" />
  <path d="M60 110 V95 L75 80" />
</svg>`;

function encodeSvg(svgString: string, color: string = "rgba(255, 255, 255, 0.28)"): string {
  const colored = svgString.replace(/currentColor/g, color);
  return `url("data:image/svg+xml,${encodeURIComponent(colored.replace(/\s+/g, ' '))}")`;
}

export const CHAT_WALLPAPERS: ChatWallpaper[] = [
  {
    id: "trading_doodle",
    name: "رسومات البورصة والتداول",
    nameEn: "Trading Doodle (WhatsApp Style)",
    category: "doodle",
    previewBg: "#0B161E",
    style: {
      backgroundColor: "#071018",
      backgroundImage: encodeSvg(TRADING_DOODLE_SVG, "rgba(56, 189, 248, 0.35)"),
      backgroundSize: "160px 160px",
      backgroundRepeat: "repeat",
    },
  },
  {
    id: "whatsapp_doodle",
    name: "رسومات واتساب الكلاسيكية",
    nameEn: "WhatsApp Classic Doodle",
    category: "doodle",
    previewBg: "#0B1E19",
    style: {
      backgroundColor: "#071713",
      backgroundImage: encodeSvg(WHATSAPP_DOODLE_SVG, "rgba(52, 211, 153, 0.35)"),
      backgroundSize: "160px 160px",
      backgroundRepeat: "repeat",
    },
  },
  {
    id: "grid",
    name: "شبكة التداول الكلاسيكية (الافتراضية)",
    nameEn: "Classic Neo-Brutalist Grid",
    category: "pattern",
    previewBg: "#000000",
    style: {
      backgroundColor: "#000000",
      backgroundImage: `
        linear-gradient(to right, rgba(255, 255, 255, 0.08) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(255, 255, 255, 0.08) 1px, transparent 1px)
      `,
      backgroundSize: "28px 28px",
      backgroundRepeat: "repeat",
    },
  },
  {
    id: "candlesticks",
    name: "مصفوفة الشموع اليابانية",
    nameEn: "Candlesticks Flow",
    category: "pattern",
    previewBg: "#11141D",
    style: {
      backgroundColor: "#090D16",
      backgroundImage: encodeSvg(CANDLESTICKS_SVG, "rgba(129, 140, 248, 0.35)"),
      backgroundSize: "100px 100px",
      backgroundRepeat: "repeat",
    },
  },
  {
    id: "dots",
    name: "مصفوفة النقاط الحديثة",
    nameEn: "Dot Matrix",
    category: "pattern",
    previewBg: "#000000",
    style: {
      backgroundColor: "#050507",
      backgroundImage: "radial-gradient(circle, rgba(255, 255, 255, 0.15) 1.2px, transparent 1.2px)",
      backgroundSize: "20px 20px",
      backgroundRepeat: "repeat",
    },
  },
  {
    id: "circuit",
    name: "دوائر الذكاء الاصطناعي (AI Circuit)",
    nameEn: "Cyber Circuit",
    category: "pattern",
    previewBg: "#0C1222",
    style: {
      backgroundColor: "#060A13",
      backgroundImage: encodeSvg(CIRCUIT_SVG, "rgba(56, 189, 248, 0.32)"),
      backgroundSize: "120px 120px",
      backgroundRepeat: "repeat",
    },
  },
  {
    id: "solid_dark",
    name: "أسود ليلي خالص (OLED Black)",
    nameEn: "Pure OLED Black",
    category: "solid",
    previewBg: "#000000",
    style: {
      backgroundColor: "#000000",
    },
  },
  {
    id: "solid_emerald",
    name: "أخضر واتساب الليلي",
    nameEn: "WhatsApp Dark Emerald",
    category: "solid",
    previewBg: "#0B1E19",
    style: {
      backgroundColor: "#061511",
    },
  },
  {
    id: "solid_navy",
    name: "كحلي منتصف الليل",
    nameEn: "Midnight Navy",
    category: "solid",
    previewBg: "#0A1224",
    style: {
      backgroundColor: "#060C18",
    },
  },
  {
    id: "solid_graphite",
    name: "رمادي الجرافيت الداكن",
    nameEn: "Graphite Slate",
    category: "solid",
    previewBg: "#18181B",
    style: {
      backgroundColor: "#111113",
    },
  },
  {
    id: "solid_amber",
    name: "قهوة داكنة دافئة",
    nameEn: "Warm Dark Espresso",
    category: "solid",
    previewBg: "#17120C",
    style: {
      backgroundColor: "#0F0B07",
    },
  },
];

export const DEFAULT_WALLPAPER_ID = "grid";
export const DEFAULT_WALLPAPER_OPACITY = 85; // 0 to 100

export function getSavedWallpaperConfig(): { id: string; opacity: number; customImage?: string } {
  if (typeof window === "undefined") {
    return { id: DEFAULT_WALLPAPER_ID, opacity: DEFAULT_WALLPAPER_OPACITY };
  }
  try {
    const id = localStorage.getItem("artoro_chat_wallpaper_id") || DEFAULT_WALLPAPER_ID;
    const rawOpacity = localStorage.getItem("artoro_chat_wallpaper_opacity");
    const opacity = rawOpacity !== null ? Math.max(10, Math.min(100, Number(rawOpacity))) : DEFAULT_WALLPAPER_OPACITY;
    const customImage = localStorage.getItem("artoro_chat_wallpaper_custom") || undefined;
    return { id, opacity, customImage };
  } catch {
    return { id: DEFAULT_WALLPAPER_ID, opacity: DEFAULT_WALLPAPER_OPACITY };
  }
}

export function saveWallpaperConfig(id: string, opacity: number, customImage?: string) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem("artoro_chat_wallpaper_id", id);
    localStorage.setItem("artoro_chat_wallpaper_opacity", String(opacity));
    if (customImage) {
      localStorage.setItem("artoro_chat_wallpaper_custom", customImage);
    } else if (id !== "custom") {
      localStorage.removeItem("artoro_chat_wallpaper_custom");
    }
    window.dispatchEvent(new CustomEvent("artoro-wallpaper-changed", { detail: { id, opacity, customImage } }));
  } catch (err) {
    console.warn("Failed to persist wallpaper preference:", err);
  }
}
