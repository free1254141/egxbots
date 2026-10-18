"use client";

import React, { createContext, useContext, useState, useEffect, useMemo, useRef } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";

export type SupportMessage = {
    id: string;
    session_id: string;
    sender: "user" | "admin";
    content: string;
    user_name: string;
    created_at: string;
    image_url?: string | null;
};

interface SupportChatContextType {
    isOpen: boolean;
    setIsOpen: (open: boolean) => void;
    messages: SupportMessage[];
    sessionId: string;
    sendMessage: (content: string, image?: string | null) => Promise<void>;
    loading: boolean;
    unreadCount: number;
    resetUnreadCount: () => void;
    isPro: boolean;
}

const SupportChatContext = createContext<SupportChatContextType | undefined>(undefined);

export function SupportChatProvider({ children }: { children: React.ReactNode }) {
    const { user } = useAuth();
    const [isOpen, setIsOpen] = useState(false);
    const [messages, setMessages] = useState<SupportMessage[]>([]);
    const [sessionId, setSessionId] = useState<string>("");
    const [loading, setLoading] = useState(false);
    const [unreadCount, setUnreadCount] = useState(0);
    const [isPro, setIsPro] = useState(false);

    const supabase = useMemo(() => createSupabaseBrowserClient(), []);

    // Check if user is a PRO subscriber
    useEffect(() => {
        if (!user) {
            setIsPro(false);
            return;
        }
        fetch("/api/user/quota", { cache: "no-store" })
            .then((res) => res.json())
            .then((data) => {
                if (data?.ok && data?.plan?.is_pro) {
                    setIsPro(true);
                } else {
                    setIsPro(false);
                }
            })
            .catch(() => setIsPro(false));
    }, [user]);

    // Load or generate session ID
    useEffect(() => {
        if (user) {
            setSessionId(user.id);
        } else {
            let storedId = localStorage.getItem("support_session_id");
            if (!storedId) {
                storedId = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2) + Date.now().toString(36);
                localStorage.setItem("support_session_id", storedId);
            }
            setSessionId(storedId);
        }
    }, [user]);

    const isOpenRef = useRef(isOpen);
    useEffect(() => {
        isOpenRef.current = isOpen;
    }, [isOpen]);

    // Load history and subscribe to changes
    useEffect(() => {
        if (!sessionId) return;

        const fetchHistory = async () => {
            try {
                const res = await fetch(`/api/support/messages?session_id=${sessionId}`);
                const data = await res.json();
                if (data.messages && Array.isArray(data.messages)) {
                    setMessages((prev) => {
                        const existingIds = new Set(data.messages.map((m: any) => m.id));
                        const optimistic = prev.filter((m) => m.id.startsWith("temp-") && !existingIds.has(m.id));
                        return [...data.messages, ...optimistic];
                    });
                }
            } catch (err) {
                console.error("Error loading chat history:", err);
            }
        };
        void fetchHistory();

        const channel = supabase
            .channel(`support-chat-provider-${sessionId}`)
            .on(
                "postgres_changes",
                {
                    event: "*",
                    schema: "public",
                    table: "support_messages",
                    filter: `session_id=eq.${sessionId}`
                },
                (payload: any) => {
                    if (payload.eventType === "DELETE") {
                        const deletedId = payload.old?.id;
                        if (deletedId) {
                            setMessages((prev) => prev.filter((m) => m.id !== deletedId));
                        } else {
                            void fetchHistory();
                        }
                        return;
                    }

                    if (payload.eventType === "INSERT") {
                        const newMsg = payload.new as SupportMessage;
                        setMessages((prev) => {
                            // 1. If we already have this message by real ID, skip
                            if (prev.some((m) => m.id === newMsg.id)) return prev;
                            // 2. If we have a matching optimistic message, replace it
                            const tempIndex = prev.findIndex((m) => m.id.startsWith("temp-") && m.content === newMsg.content && m.sender === newMsg.sender);
                            if (tempIndex > -1) {
                                const list = [...prev];
                                list[tempIndex] = newMsg;
                                return list;
                            }
                            return [...prev, newMsg];
                        });

                        // If widget is closed and message is from admin, increment unreadCount
                        if (newMsg.sender === "admin" && !isOpenRef.current) {
                            setUnreadCount((c) => c + 1);
                        }
                    }
                }
            )
            .subscribe();

        return () => {
            void supabase.removeChannel(channel);
        };
    }, [sessionId, supabase]);

    // Fallback polling while the chat is open. Realtime (above) delivers new
    // messages instantly; this only covers dropped websocket events, so it runs
    // every 30s and pauses while the tab is hidden.
    useEffect(() => {
        if (!sessionId || !isOpen) return;

        const interval = setInterval(async () => {
            if (typeof document !== "undefined" && document.hidden) return;
            try {
                const res = await fetch(`/api/support/messages?session_id=${sessionId}`);
                const data = await res.json();
                if (data.messages && Array.isArray(data.messages)) {
                    setMessages((prev) => {
                        const prevIds = new Set(prev.map((m) => m.id));
                        const hasNew = data.messages.some((m: any) => !prevIds.has(m.id));
                        if (!hasNew && prev.length === data.messages.length) return prev;
                        const existingIds = new Set(data.messages.map((m: any) => m.id));
                        const optimistic = prev.filter((m) => m.id.startsWith("temp-") && !existingIds.has(m.id));
                        return [...data.messages, ...optimistic];
                    });
                }
            } catch {
                // silent background catch
            }
        }, 30000);

        return () => clearInterval(interval);
    }, [sessionId, isOpen]);

    // Background fallback while closed (every 60 seconds, visible tabs only) to
    // update the unread badge if a realtime event was missed.
    useEffect(() => {
        if (!sessionId || isOpen || !isPro) return;

        const interval = setInterval(async () => {
            if (typeof document !== "undefined" && document.hidden) return;
            try {
                const res = await fetch(`/api/support/messages?session_id=${sessionId}`);
                const data = await res.json();
                if (data.messages && Array.isArray(data.messages)) {
                    setMessages((prev) => {
                        const prevIds = new Set(prev.map((m) => m.id));
                        const newAdminMessages = data.messages.filter((m: any) => m.sender === "admin" && !prevIds.has(m.id));
                        if (newAdminMessages.length > 0) {
                            setUnreadCount((c) => c + newAdminMessages.length);
                        }
                        return data.messages;
                    });
                }
            } catch {
                // silent
            }
        }, 60000);

        return () => clearInterval(interval);
    }, [sessionId, isOpen, isPro]);

    // Reset unread count when opening the widget
    useEffect(() => {
        if (isOpen) {
            setUnreadCount(0);
        }
    }, [isOpen]);

    const sendMessage = async (content: string, image?: string | null) => {
        const trimmedContent = content.trim();
        if ((!trimmedContent && !image) || !sessionId) return;
        setLoading(true);

        const userName = user?.user_metadata?.full_name || user?.user_metadata?.name || user?.email?.split("@")[0] || "Guest";

        // Create and append an optimistic message instantly
        const tempId = "temp-" + Math.random().toString(36).substring(2) + Date.now().toString(36);
        const optimisticMsg: SupportMessage = {
            id: tempId,
            session_id: sessionId,
            sender: "user",
            content: trimmedContent || (image ? "صورة مرفقة" : ""),
            user_name: userName,
            created_at: new Date().toISOString(),
            image_url: image || undefined
        };

        setMessages((prev) => [...prev, optimisticMsg]);

        try {
            const res = await fetch("/api/support/message", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    session_id: sessionId,
                    content: trimmedContent,
                    image: image || null,
                    user_name: userName
                })
            });
            const data = await res.json();
            if (data.ok && data.message) {
                // Replace optimistic message with actual DB message (which has database ID and fields)
                setMessages((prev) =>
                    prev.map((m) => m.id === tempId ? data.message : m)
                );
            }
        } catch (err) {
            console.error("Error sending message:", err);
            // Rollback optimistic message on error
            setMessages((prev) => prev.filter((m) => m.id !== tempId));
        } finally {
            setLoading(false);
        }
    };

    const value = useMemo(() => ({
        isOpen,
        setIsOpen,
        messages,
        sessionId,
        sendMessage,
        loading,
        unreadCount,
        resetUnreadCount: () => setUnreadCount(0),
        isPro,
    }), [isOpen, messages, sessionId, loading, unreadCount, isPro]);

    return (
        <SupportChatContext.Provider value={value}>
            {children}
        </SupportChatContext.Provider>
    );
}

export function useOptionalSupportChat() {
    return useContext(SupportChatContext);
}

export function useSupportChat() {
    const context = useContext(SupportChatContext);
    if (!context) {
        throw new Error("useSupportChat must be used within a SupportChatProvider");
    }
    return context;
}
