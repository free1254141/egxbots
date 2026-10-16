"use client";

import React, { useState, useRef, useEffect } from "react";
import { usePathname } from "next/navigation";
import { useLanguage } from "@/contexts/LanguageContext";
import { useSupportChat } from "@/contexts/SupportChatContext";
import { Send, X, Crown, User, Headphones, Loader2, Maximize2, Minimize2 } from "lucide-react";

export default function SupportChatWidget() {
    const pathname = usePathname();
    const { language } = useLanguage();
    const isAr = language === "ar";

    const {
        isOpen,
        setIsOpen,
        messages,
        sendMessage,
        loading,
        unreadCount,
        isPro,
    } = useSupportChat();

    const [input, setInput] = useState("");
    const [isExpanded, setIsExpanded] = useState(false);
    const messagesContainerRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // Load expanded preference
    useEffect(() => {
        try {
            const saved = localStorage.getItem("support_chat_expanded");
            if (saved === "true") setIsExpanded(true);
        } catch {
            // ignore
        }
    }, []);

    const toggleExpand = () => {
        setIsExpanded((prev) => {
            const next = !prev;
            try {
                localStorage.setItem("support_chat_expanded", String(next));
            } catch {
                // ignore
            }
            return next;
        });
    };

    // Scroll to bottom whenever messages change or window opens
    useEffect(() => {
        if (isOpen) {
            const container = messagesContainerRef.current;
            if (container) {
                container.scrollTop = container.scrollHeight;
            }
        }
    }, [messages, isOpen, isExpanded]);

    // Only render for PRO members and do not overlay on admin panels
    if (!isPro || pathname?.startsWith("/admin")) {
        return null;
    }

    const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        setInput(e.target.value);
        const textarea = textareaRef.current;
        if (textarea) {
            textarea.style.height = "auto";
            textarea.style.height = `${Math.min(textarea.scrollHeight, 130)}px`;
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || loading) return;

        const content = input.trim();
        setInput("");
        if (textareaRef.current) {
            textareaRef.current.style.height = "auto";
        }
        await sendMessage(content);
    };

    if (!isOpen) {
        return (
            <button
                onClick={() => setIsOpen(true)}
                className="fixed bottom-5 right-[96px] sm:right-[102px] z-[9998] flex h-[72px] w-[72px] flex-col items-center justify-center rounded-[24px] border-2 border-black dark:border-white bg-gradient-to-br from-amber-400 via-amber-500 to-amber-600 p-2 shadow-[0_12px_34px_rgba(217,119,6,0.35)] dark:shadow-[0_12px_34px_rgba(0,0,0,0.5)] transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_18px_42px_rgba(217,119,6,0.48)] active:translate-y-0 animate-in fade-in zoom-in group"
                aria-label={isAr ? "خدمة عملاء VIP" : "VIP Customer Support"}
                title={isAr ? "خدمة عملاء VIP للمشتركين" : "VIP Support for Pro Subscribers"}
            >
                <div className="relative flex items-center justify-center">
                    <Headphones className="h-6 w-6 text-black stroke-[2.4]" />
                    <Crown className="h-4 w-4 text-amber-950 absolute -top-3 -right-3 fill-amber-200 stroke-[2]" />
                </div>
                <span className="text-[10px] font-black uppercase tracking-wider text-black mt-1">
                    {isAr ? "دعم VIP" : "VIP"}
                </span>
                {unreadCount > 0 && (
                    <span className="absolute -top-1.5 -right-1.5 h-6 w-6 bg-red-600 border-2 border-white dark:border-black rounded-full text-[10px] font-black text-white flex items-center justify-center animate-bounce shadow-lg">
                        {unreadCount}
                    </span>
                )}
            </button>
        );
    }

    return (
        <div
            className={`
                fixed bottom-24 right-4 sm:right-6 z-[9999] rounded-2xl border-4 border-black dark:border-white
                bg-white dark:bg-zinc-950 text-black dark:text-white
                shadow-[8px_8px_0px_0px_#000000] dark:shadow-[8px_8px_0px_0px_rgba(255,255,255,0.25)]
                flex flex-col animate-in fade-in slide-in-from-bottom-5 duration-200 overflow-hidden
                transition-all
                ${isExpanded
                    ? "w-[calc(100vw-32px)] sm:w-[680px] md:w-[780px] h-[720px] sm:h-[780px] max-h-[90vh]"
                    : "w-[calc(100vw-32px)] sm:w-[460px] md:w-[500px] h-[580px] sm:h-[620px] max-h-[82vh]"
                }
            `}
            dir={isAr ? "rtl" : "ltr"}
        >
            {/* Header */}
            <div className="bg-gradient-to-r from-amber-400 via-amber-400 to-amber-500 text-black border-b-4 border-black p-3.5 flex items-center justify-between flex-shrink-0">
                <div className="flex items-center gap-2.5">
                    <div className="h-10 w-10 bg-black text-amber-400 flex items-center justify-center border-2 border-black rounded-xl shrink-0">
                        <Headphones className="h-5 w-5" />
                    </div>
                    <div>
                        <div className="flex items-center gap-1.5 font-black uppercase text-xs sm:text-sm tracking-tight text-black">
                            <span>{isAr ? "خدمة عملاء VIP" : "EGX BOTS VIP Support"}</span>
                            <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-black text-amber-300 text-[9px] font-black rounded-md">
                                <Crown className="w-2.5 h-2.5 fill-amber-300" />
                                PRO
                            </span>
                        </div>
                        <div className="text-[10px] font-bold text-zinc-900/80">
                            {isAr ? "مباشر مع إدارة المنصة (تليجرام)" : "Direct Admin Desk via Telegram"}
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-1">
                    {/* Expand/Minimize Button */}
                    <button
                        type="button"
                        onClick={toggleExpand}
                        className="p-1.5 rounded-lg hover:bg-black/10 border-2 border-transparent hover:border-black transition-colors"
                        title={isExpanded ? (isAr ? "تصغير النافذة" : "Restore size") : (isAr ? "تكبير النافذة" : "Maximize window")}
                        aria-label={isExpanded ? "تصغير النافذة" : "تكبير النافذة"}
                    >
                        {isExpanded ? (
                            <Minimize2 className="h-4 w-4 text-black stroke-[2.5]" />
                        ) : (
                            <Maximize2 className="h-4 w-4 text-black stroke-[2.5]" />
                        )}
                    </button>

                    {/* Close Button */}
                    <button
                        type="button"
                        onClick={() => setIsOpen(false)}
                        className="p-1.5 rounded-lg hover:bg-black/10 border-2 border-transparent hover:border-black transition-colors"
                        aria-label={isAr ? "إغلاق" : "Close"}
                        title={isAr ? "إغلاق النافذة" : "Close window"}
                    >
                        <X className="h-4 w-4 text-black stroke-[2.5]" />
                    </button>
                </div>
            </div>

            {/* Message Area */}
            <div
                ref={messagesContainerRef}
                className="flex-1 overflow-y-auto p-4 space-y-3.5 custom-scrollbar bg-zinc-50 dark:bg-zinc-950 font-sans text-xs"
            >
                {messages.length === 0 ? (
                    <div className="text-center py-10 px-4 space-y-3">
                        <div className="h-14 w-14 mx-auto bg-amber-100 dark:bg-amber-950/40 border-2 border-black dark:border-white rounded-2xl flex items-center justify-center shadow-[3px_3px_0px_#000]">
                            <Crown className="h-7 w-7 text-amber-600 dark:text-amber-400" />
                        </div>
                        <h4 className="font-black text-base text-black dark:text-white">
                            {isAr ? "أهلاً بك في دعم المشتركين VIP 👑" : "Welcome to VIP Support 👑"}
                        </h4>
                        <p className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed max-w-sm mx-auto font-medium">
                            {isAr
                                ? "رسالتك هنا تصل مباشرة لإدارة المنصة على تليجرام، ويصلك الرد هنا لحظياً مع إشعار بالرسائل الجديدة."
                                : "Your messages are forwarded directly to the admin desk on Telegram, and replies are synced here in real time."}
                        </p>
                    </div>
                ) : (
                    messages.map((msg) => (
                        <div
                            key={msg.id}
                            className={`flex gap-2.5 ${msg.sender === "user" ? "flex-row-reverse" : "flex-row"}`}
                        >
                            <div className={`
                                h-8 w-8 rounded-xl flex items-center justify-center shrink-0 border-2 border-black
                                ${msg.sender === "user"
                                    ? "bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 border-zinc-400 dark:border-zinc-600"
                                    : "bg-amber-400 text-black border-black shadow-[2px_2px_0px_#000]"}
                            `}>
                                {msg.sender === "user" ? <User className="h-4 w-4" /> : <Crown className="h-4 w-4" />}
                            </div>
                            <div className={`
                                max-w-[82%] rounded-xl p-3.5 border-2 shadow-[3px_3px_0px_rgba(0,0,0,0.15)] dark:shadow-[3px_3px_0px_rgba(255,255,255,0.08)]
                                ${msg.sender === "user"
                                    ? "bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 border-black dark:border-zinc-700"
                                    : "bg-amber-100 dark:bg-amber-950/40 border-amber-500 text-amber-950 dark:text-amber-100 font-medium"}
                            `}>
                                {msg.sender === "admin" && (
                                    <div className="text-[10px] font-black text-amber-800 dark:text-amber-400 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                                        <Crown className="w-3 h-3 fill-amber-400" />
                                        {msg.user_name || (isAr ? "الدعم الفني VIP" : "VIP Support Desk")}
                                    </div>
                                )}
                                <div className="whitespace-pre-wrap leading-relaxed text-xs sm:text-sm font-sans">{msg.content}</div>
                                <div className="text-[10px] text-zinc-400 dark:text-zinc-500 mt-1.5 text-end font-mono">
                                    {msg.created_at ? new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
                                </div>
                            </div>
                        </div>
                    ))
                )}
            </div>

            {/* Input Form */}
            <form onSubmit={handleSubmit} className="p-3 border-t-2 border-black dark:border-zinc-800 bg-white dark:bg-zinc-900 flex items-end gap-2 flex-shrink-0">
                <div className="flex-1 min-w-0">
                    <textarea
                        ref={textareaRef}
                        rows={1}
                        value={input}
                        onChange={handleInputChange}
                        onKeyDown={handleKeyDown}
                        placeholder={isAr ? "اكتب استفسارك هنا مباشرة... (Enter للإرسال)" : "Type your message to support... (Enter to send)"}
                        className="w-full resize-none min-h-[44px] max-h-[130px] rounded-xl bg-zinc-50 dark:bg-zinc-950 border-2 border-black dark:border-zinc-700 px-3 py-2.5 text-xs sm:text-sm text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 dark:placeholder:text-zinc-500 focus:border-amber-500 focus:ring-1 focus:ring-amber-500 focus:outline-none transition-colors custom-scrollbar leading-relaxed"
                    />
                </div>
                <button
                    type="submit"
                    disabled={loading || !input.trim()}
                    className="h-11 w-11 shrink-0 rounded-xl bg-amber-400 hover:bg-amber-300 border-2 border-black text-black font-black text-xs sm:text-sm flex items-center justify-center transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-[2px_2px_0px_#000000] active:translate-y-0.5 active:shadow-none"
                    title={isAr ? "إرسال (Enter)" : "Send (Enter)"}
                >
                    {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </button>
            </form>
        </div>
    );
}
