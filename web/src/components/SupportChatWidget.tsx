"use client";

import React, { useState, useRef, useEffect } from "react";
import { useLanguage } from "@/contexts/LanguageContext";
import { useSupportChat } from "@/contexts/SupportChatContext";
import { Send, X, MessageSquare, Crown, User, Headphones, Loader2 } from "lucide-react";

export default function SupportChatWidget() {
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
    const messagesContainerRef = useRef<HTMLDivElement>(null);

    // Scroll to bottom whenever messages change or window opens
    useEffect(() => {
        if (isOpen) {
            const container = messagesContainerRef.current;
            if (container) {
                container.scrollTop = container.scrollHeight;
            }
        }
    }, [messages, isOpen]);

    // Only render for PRO members
    if (!isPro) {
        return null;
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || loading) return;

        const content = input.trim();
        setInput("");
        await sendMessage(content);
    };

    if (!isOpen) {
        return (
            <button
                onClick={() => setIsOpen(true)}
                className="fixed bottom-5 left-5 h-14 w-14 sm:h-16 sm:w-16 rounded-2xl bg-gradient-to-br from-amber-400 to-amber-500 hover:from-amber-300 hover:to-amber-400 border-4 border-black dark:border-white text-black flex flex-col items-center justify-center shadow-[4px_4px_0px_0px_#000000] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.4)] transition-all hover:scale-105 active:translate-y-1 active:shadow-none z-[9998] group"
                aria-label={isAr ? "خدمة عملاء VIP" : "VIP Customer Support"}
                title={isAr ? "خدمة عملاء VIP للمشتركين" : "VIP Support for Pro Subscribers"}
            >
                <div className="relative flex items-center justify-center">
                    <Headphones className="h-6 w-6 text-black" />
                    <Crown className="h-3.5 w-3.5 text-amber-900 absolute -top-2.5 -right-2.5 fill-amber-300" />
                </div>
                <span className="text-[9px] font-black uppercase tracking-wider text-black mt-0.5">
                    {isAr ? "دعم VIP" : "VIP"}
                </span>
                {unreadCount > 0 && (
                    <span className="absolute -top-2 -right-2 h-6 w-6 bg-red-600 border-2 border-black dark:border-white rounded-full text-[10px] font-black text-white flex items-center justify-center animate-bounce shadow-md">
                        {unreadCount}
                    </span>
                )}
            </button>
        );
    }

    return (
        <div
            className="fixed bottom-20 sm:bottom-24 left-4 sm:left-5 w-[calc(100vw-32px)] sm:w-[380px] h-[520px] max-h-[78vh] rounded-none border-4 border-black dark:border-white bg-white dark:bg-zinc-950 text-black dark:text-white shadow-[6px_6px_0px_0px_#000000] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.2)] flex flex-col z-[9999] animate-in fade-in slide-in-from-bottom-5 duration-200 overflow-hidden"
            dir={isAr ? "rtl" : "ltr"}
        >
            {/* Header */}
            <div className="bg-gradient-to-r from-amber-400 to-amber-500 text-black border-b-4 border-black p-3.5 flex items-center justify-between flex-shrink-0">
                <div className="flex items-center gap-2">
                    <div className="h-9 w-9 bg-black text-amber-400 flex items-center justify-center border-2 border-black shrink-0">
                        <Headphones className="h-5 w-5" />
                    </div>
                    <div>
                        <div className="flex items-center gap-1.5 font-black uppercase text-xs sm:text-sm tracking-tight text-black">
                            <span>{isAr ? "خدمة عملاء VIP" : "EGX BOTS VIP Support"}</span>
                            <span className="inline-flex items-center gap-0.5 px-1.5 py-0.2 bg-black text-amber-300 text-[9px] font-black rounded-none">
                                <Crown className="w-2.5 h-2.5 fill-amber-300" />
                                PRO
                            </span>
                        </div>
                        <div className="text-[10px] font-bold text-zinc-900/80">
                            {isAr ? "مباشر مع إدارة المنصة" : "Direct Admin Desk"}
                        </div>
                    </div>
                </div>
                <button
                    onClick={() => setIsOpen(false)}
                    className="p-1.5 rounded-none hover:bg-black/10 border-2 border-transparent hover:border-black transition-colors"
                    aria-label={isAr ? "إغلاق" : "Close"}
                >
                    <X className="h-4 w-4 text-black" />
                </button>
            </div>

            {/* Message Area */}
            <div
                ref={messagesContainerRef}
                className="flex-1 overflow-y-auto p-4 space-y-3.5 custom-scrollbar bg-zinc-50 dark:bg-zinc-950 font-sans text-xs"
            >
                {messages.length === 0 ? (
                    <div className="text-center py-8 px-4 space-y-2">
                        <div className="h-12 w-12 mx-auto bg-amber-100 dark:bg-amber-950/40 border-2 border-black dark:border-white flex items-center justify-center">
                            <Crown className="h-6 w-6 text-amber-600 dark:text-amber-400" />
                        </div>
                        <h4 className="font-black text-sm text-black dark:text-white">
                            {isAr ? "أهلاً بك في دعم المشتركين VIP 👑" : "Welcome to VIP Support 👑"}
                        </h4>
                        <p className="text-[11px] text-zinc-600 dark:text-zinc-400 leading-relaxed max-w-xs mx-auto">
                            {isAr
                                ? "رسالتك هنا تصل مباشرة لإدارة المنصة على تليجرام، وسيتم الرد عليك هنا في أسرع وقت."
                                : "Your messages here are delivered directly to the platform admin desk, and replies appear here instantly."}
                        </p>
                    </div>
                ) : (
                    messages.map((msg) => (
                        <div
                            key={msg.id}
                            className={`flex gap-2 ${msg.sender === "user" ? "flex-row-reverse" : "flex-row"}`}
                        >
                            <div className={`
                                h-7 w-7 rounded-none flex items-center justify-center shrink-0 border-2 border-black
                                ${msg.sender === "user"
                                    ? "bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 border-zinc-400 dark:border-zinc-600"
                                    : "bg-amber-400 text-black border-black"}
                            `}>
                                {msg.sender === "user" ? <User className="h-3.5 w-3.5" /> : <Crown className="h-3.5 w-3.5" />}
                            </div>
                            <div className={`
                                max-w-[80%] rounded-none p-3 border-2 shadow-[2px_2px_0px_rgba(0,0,0,0.15)] dark:shadow-[2px_2px_0px_rgba(255,255,255,0.05)]
                                ${msg.sender === "user"
                                    ? "bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 border-black dark:border-zinc-700"
                                    : "bg-amber-100 dark:bg-amber-950/40 border-amber-500 text-amber-950 dark:text-amber-100 font-medium"}
                            `}>
                                {msg.sender === "admin" && (
                                    <div className="text-[9px] font-black text-amber-800 dark:text-amber-400 uppercase tracking-wider mb-1 flex items-center gap-1">
                                        <Crown className="w-2.5 h-2.5" />
                                        {msg.user_name || (isAr ? "الدعم الفني VIP" : "VIP Support Desk")}
                                    </div>
                                )}
                                <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
                                <div className="text-[9px] text-zinc-400 dark:text-zinc-500 mt-1 text-end font-mono">
                                    {msg.created_at ? new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
                                </div>
                            </div>
                        </div>
                    ))
                )}
            </div>

            {/* Input Form */}
            <form onSubmit={handleSubmit} className="p-3 border-t-4 border-black dark:border-white bg-white dark:bg-zinc-900 flex gap-2 flex-shrink-0">
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder={isAr ? "اكتب استفسارك هنا مباشرة..." : "Type your message to support..."}
                    className="flex-1 h-10 rounded-none bg-zinc-50 dark:bg-zinc-950 border-2 border-black dark:border-zinc-700 px-3 text-xs text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 dark:placeholder:text-zinc-500 focus:border-amber-500 focus:outline-none transition-colors"
                />
                <button
                    type="submit"
                    disabled={loading || !input.trim()}
                    className="h-10 px-3 rounded-none bg-amber-400 hover:bg-amber-300 border-2 border-black text-black font-black text-xs flex items-center justify-center gap-1 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-[2px_2px_0px_#000000]"
                >
                    {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </button>
            </form>
        </div>
    );
}
