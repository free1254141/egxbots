"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  X,
  Check,
  Palette,
  Sparkles,
  Sliders,
  Upload,
  Trash2,
  RotateCcw,
  Image as ImageIcon,
} from "lucide-react";
import {
  CHAT_WALLPAPERS,
  DEFAULT_WALLPAPER_ID,
  DEFAULT_WALLPAPER_OPACITY,
  saveWallpaperConfig,
  type ChatWallpaper,
} from "@/lib/chat-wallpapers";

interface ChatWallpaperModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentId: string;
  currentOpacity: number;
  currentCustomImage?: string;
  onApply: (id: string, opacity: number, customImage?: string) => void;
  isAr?: boolean;
}

export function ChatWallpaperModal({
  isOpen,
  onClose,
  currentId,
  currentOpacity,
  currentCustomImage,
  onApply,
  isAr = true,
}: ChatWallpaperModalProps) {
  const [selectedId, setSelectedId] = useState<string>(currentId || DEFAULT_WALLPAPER_ID);
  const [opacity, setOpacity] = useState<number>(currentOpacity ?? DEFAULT_WALLPAPER_OPACITY);
  const [customImage, setCustomImage] = useState<string | undefined>(currentCustomImage);
  const [activeTab, setActiveTab] = useState<"doodle" | "solid" | "custom">("doodle");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setSelectedId(currentId || DEFAULT_WALLPAPER_ID);
      setOpacity(currentOpacity ?? DEFAULT_WALLPAPER_OPACITY);
      setCustomImage(currentCustomImage);
      if (currentId === "custom") {
        setActiveTab("custom");
      } else {
        const found = CHAT_WALLPAPERS.find((w) => w.id === currentId);
        if (found?.category === "solid") {
          setActiveTab("solid");
        } else {
          setActiveTab("doodle");
        }
      }
    }
  }, [isOpen, currentId, currentOpacity, currentCustomImage]);

  if (!isOpen) return null;

  const handleSelect = (wallpaper: ChatWallpaper) => {
    setSelectedId(wallpaper.id);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 3 * 1024 * 1024) {
      alert(isAr ? "حجم الصورة كبير جداً، يرجى اختيار صورة أصغر من 3 ميجابايت" : "Image size too large, please select an image under 3MB");
      return;
    }

    const reader = new FileReader();
    reader.onload = (event) => {
      const dataUrl = event.target?.result as string;
      setCustomImage(dataUrl);
      setSelectedId("custom");
    };
    reader.readAsDataURL(file);
  };

  const handleRemoveCustomImage = () => {
    setCustomImage(undefined);
    if (selectedId === "custom") {
      setSelectedId(DEFAULT_WALLPAPER_ID);
    }
  };

  const handleSave = () => {
    saveWallpaperConfig(selectedId, opacity, selectedId === "custom" ? customImage : undefined);
    onApply(selectedId, opacity, selectedId === "custom" ? customImage : undefined);
    onClose();
  };

  const handleResetDefault = () => {
    setSelectedId(DEFAULT_WALLPAPER_ID);
    setOpacity(DEFAULT_WALLPAPER_OPACITY);
    setCustomImage(undefined);
  };

  const doodleWallpapers = CHAT_WALLPAPERS.filter((w) => w.category === "doodle" || w.category === "pattern");
  const solidWallpapers = CHAT_WALLPAPERS.filter((w) => w.category === "solid");

  return (
    <div
      className="fixed inset-0 z-[100000] flex items-center justify-center p-3 sm:p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200"
      dir={isAr ? "rtl" : "ltr"}
    >
      <div className="relative w-full max-w-xl max-h-[90vh] flex flex-col bg-zinc-950 border-4 border-black dark:border-white shadow-[6px_6px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_rgba(255,255,255,0.25)] rounded-2xl overflow-hidden text-white">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b-2 border-zinc-800 bg-zinc-900/90">
          <div className="flex items-center gap-2.5">
            <span className="p-2 bg-amber-400 text-black border-2 border-black rounded-lg shadow-[2px_2px_0px_rgba(0,0,0,1)]">
              <Palette className="w-4 h-4" />
            </span>
            <div>
              <h3 className="text-base font-black tracking-tight text-white">
                {isAr ? "خلفية المحادثة (ورق حائط)" : "Chat Wallpaper Settings"}
              </h3>
              <p className="text-[11px] font-semibold text-zinc-400">
                {isAr ? "اختر نمط الخلفية والرسومات مثل واتساب وتليجرام" : "Choose chat doodle wallpaper like WhatsApp"}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg border border-zinc-700 bg-zinc-900 text-zinc-400 hover:text-white hover:bg-zinc-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Category Tabs */}
        <div className="flex items-center gap-2 px-5 pt-3 border-b border-zinc-800/80 bg-zinc-900/40 text-xs font-black">
          <button
            onClick={() => setActiveTab("doodle")}
            className={`flex items-center gap-1.5 pb-2.5 px-3 border-b-2 transition ${
              activeTab === "doodle"
                ? "border-amber-400 text-amber-400"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>{isAr ? "رسومات وأنماط" : "Doodles & Patterns"}</span>
          </button>
          <button
            onClick={() => setActiveTab("solid")}
            className={`flex items-center gap-1.5 pb-2.5 px-3 border-b-2 transition ${
              activeTab === "solid"
                ? "border-amber-400 text-amber-400"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <span className="w-3.5 h-3.5 rounded bg-zinc-700 border border-zinc-500 inline-block" />
            <span>{isAr ? "ألوان داكنة" : "Solid Colors"}</span>
          </button>
          <button
            onClick={() => setActiveTab("custom")}
            className={`flex items-center gap-1.5 pb-2.5 px-3 border-b-2 transition ${
              activeTab === "custom"
                ? "border-amber-400 text-amber-400"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <ImageIcon className="w-3.5 h-3.5" />
            <span>{isAr ? "صورة مخصصة" : "Custom Image"}</span>
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {activeTab === "doodle" && (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {doodleWallpapers.map((w) => {
                const isSelected = selectedId === w.id;
                return (
                  <button
                    key={w.id}
                    onClick={() => handleSelect(w)}
                    className={`group relative flex flex-col items-center justify-between h-32 rounded-xl p-2.5 text-right border-2 transition overflow-hidden text-xs font-bold ${
                      isSelected
                        ? "border-amber-400 shadow-[0_0_12px_rgba(251,191,36,0.3)] ring-2 ring-amber-400/50"
                        : "border-zinc-800 hover:border-zinc-600 bg-zinc-900/60"
                    }`}
                  >
                    {/* Wallpaper Preview Swatch */}
                    <div
                      className="absolute inset-0 z-0 transition group-hover:scale-105"
                      style={w.style}
                    />
                    <div className="absolute inset-0 z-1 bg-black/20 group-hover:bg-transparent transition" />

                    {/* Checkmark Badge */}
                    <div className="relative z-10 w-full flex justify-between items-start">
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-black/70 border border-white/20 text-zinc-300 backdrop-blur-sm">
                        {w.category === "doodle" ? (isAr ? "رسم" : "Doodle") : (isAr ? "نمط" : "Pattern")}
                      </span>
                      {isSelected && (
                        <span className="w-5 h-5 rounded-full bg-amber-400 text-black flex items-center justify-center border border-black shadow-xs">
                          <Check className="w-3 h-3 stroke-[3]" />
                        </span>
                      )}
                    </div>

                    {/* Label */}
                    <div className="relative z-10 w-full p-1.5 rounded-lg bg-black/80 backdrop-blur-md border border-white/10 text-center">
                      <span className="text-[11px] font-black text-white block truncate">
                        {isAr ? w.name : w.nameEn}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {activeTab === "solid" && (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {solidWallpapers.map((w) => {
                const isSelected = selectedId === w.id;
                return (
                  <button
                    key={w.id}
                    onClick={() => handleSelect(w)}
                    className={`group relative flex flex-col items-center justify-between h-28 rounded-xl p-2.5 text-right border-2 transition overflow-hidden text-xs font-bold ${
                      isSelected
                        ? "border-amber-400 shadow-[0_0_12px_rgba(251,191,36,0.3)] ring-2 ring-amber-400/50"
                        : "border-zinc-800 hover:border-zinc-600"
                    }`}
                    style={w.style}
                  >
                    <div className="w-full flex justify-end">
                      {isSelected && (
                        <span className="w-5 h-5 rounded-full bg-amber-400 text-black flex items-center justify-center border border-black shadow-xs">
                          <Check className="w-3 h-3 stroke-[3]" />
                        </span>
                      )}
                    </div>
                    <div className="w-full p-1.5 rounded-lg bg-black/60 backdrop-blur-sm border border-white/10 text-center">
                      <span className="text-[11px] font-black text-white block truncate">
                        {isAr ? w.name : w.nameEn}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {activeTab === "custom" && (
            <div className="space-y-4">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleFileUpload}
                className="hidden"
              />

              {customImage ? (
                <div className="relative h-44 rounded-xl border-2 border-amber-400 overflow-hidden group shadow-md">
                  <div
                    className="absolute inset-0 bg-cover bg-center"
                    style={{ backgroundImage: `url(${customImage})` }}
                  />
                  <div className="absolute inset-0 bg-black/40 group-hover:bg-black/20 transition" />
                  <div className="absolute top-3 right-3 flex items-center gap-2">
                    <span className="px-2 py-1 rounded bg-black/80 text-amber-400 text-xs font-black border border-white/10">
                      {isAr ? "صورة مخصصة جاهزة" : "Custom Ready"}
                    </span>
                    <button
                      onClick={handleRemoveCustomImage}
                      className="p-1.5 rounded-lg bg-rose-600/90 text-white hover:bg-rose-600 border border-white/20 transition"
                      title={isAr ? "حذف الصورة" : "Remove Image"}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="absolute bottom-3 left-3 right-3">
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="w-full py-2 bg-black/80 hover:bg-black text-xs font-black text-white rounded-lg border border-white/20 transition"
                    >
                      {isAr ? "تغيير الصورة..." : "Change Image..."}
                    </button>
                  </div>
                </div>
              ) : (
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="flex flex-col items-center justify-center h-44 rounded-xl border-2 border-dashed border-zinc-700 hover:border-amber-400/80 bg-zinc-900/50 hover:bg-zinc-900/80 transition cursor-pointer p-6 text-center group"
                >
                  <span className="p-3 rounded-full bg-zinc-800 group-hover:bg-amber-400 group-hover:text-black text-zinc-300 transition mb-2">
                    <Upload className="w-6 h-6" />
                  </span>
                  <p className="text-xs font-black text-zinc-200">
                    {isAr ? "اضغط لاختيار صورة خلفية من جهازك" : "Click to select a background image"}
                  </p>
                  <p className="text-[11px] text-zinc-500 mt-1">
                    {isAr ? "يدعم JPG, PNG, WebP (بحد أقصى 3 ميجابايت)" : "Supports JPG, PNG, WebP (max 3MB)"}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Dimming / Opacity Slider (Like WhatsApp) */}
          <div className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-900/70 space-y-2">
            <div className="flex items-center justify-between text-xs font-black">
              <span className="flex items-center gap-1.5 text-zinc-300">
                <Sliders className="w-3.5 h-3.5 text-amber-400" />
                <span>{isAr ? "تعتيم ورق الحائط (وضوح النصوص):" : "Wallpaper Dimming (Readability):"}</span>
              </span>
              <span className="font-mono text-amber-400">{opacity}%</span>
            </div>
            <input
              type="range"
              min="15"
              max="100"
              step="5"
              value={opacity}
              onChange={(e) => setOpacity(Number(e.target.value))}
              className="w-full h-2 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-amber-400"
            />
            <div className="flex justify-between text-[10px] font-semibold text-zinc-500">
              <span>{isAr ? "خافت جداً" : "Faint"}</span>
              <span>{isAr ? "واضح وبارز" : "Vivid"}</span>
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between px-5 py-3.5 border-t-2 border-zinc-800 bg-zinc-900/90 gap-3">
          <button
            onClick={handleResetDefault}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-black text-zinc-400 hover:text-white border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 transition"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>{isAr ? "الافتراضي" : "Reset Default"}</span>
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-black text-zinc-400 hover:text-white transition"
            >
              {isAr ? "إلغاء" : "Cancel"}
            </button>
            <button
              onClick={handleSave}
              className="inline-flex items-center gap-1.5 px-5 py-2 rounded-xl text-xs font-black bg-amber-400 hover:bg-amber-300 text-black border-2 border-black shadow-[2px_2px_0px_rgba(0,0,0,1)] transition active:translate-y-0.5"
            >
              <Check className="w-4 h-4 stroke-[2.5]" />
              <span>{isAr ? "تطبيق وحفظ" : "Apply & Save"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
