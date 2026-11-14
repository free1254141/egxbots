"use client";

import React, { createContext, useContext, useState, useEffect, useMemo, useRef } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";
import { fetchUserQuotaCached } from "@/lib/user-quota-client";

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

    // Check if user is a PRO subscriber using shared 30m deduplicated quota client
    useEffect(() => {
        if (!user?.id) {
            setIsPro(false);
            return;
        }
        let active = true;
        void fetchUserQuotaCached(user.id)
            .then((data) => {
                if (!active) return;
                setIsPro(Boolean(data?.ok && data?.plan?.is_pro));
            })
            .catch(() => {
                if (active) setIsPro(false);
            });
        return () => {
            active = false;
        };
    }, [user?.id]);

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

    // /api/support/messages only answers for the signed-in owner of the session.
    // Guests (random localStorage id) and the render where `user` is set but
    // `sessionId` still holds the old guest id only produced 401/403 invocations.
    const canReadHistory = Boolean(user) && sessionId === user?.id;

    const isOpenRef = useRef(isOpen);
    const [hasInteracted, setHasInteracted] = useState(false);
    useEffect(() => {
        isOpenRef.current = isOpen;
        if (isOpen) {
            setHasInteracted(true);
        }
    }, [isOpen]);

    // Newest confirmed (non-optimistic) message, used for incremental polling.
    const messagesRef = useRef<SupportMessage[]>([]);
    useEffect(() => {
        messagesRef.current = messages;
    }, [messages]);

    // Load history and subscribe to changes ONLY when the chat is opened by the user,
    // or if the user has active messages in this session.
    // Passive visitors who never touch the support chat should never hold a persistent
    // Supabase Realtime WebSocket channel with recurring heartbeats and logs.
    useEffect(() => {
        if (!sessionId || (!isOpen && !hasInteracted && messages.length === 0)) return;

        const fetchHistory = async () => {
            if (!canReadHistory) return;
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
    }, [sessionId, supabase, canReadHistory, isOpen, hasInteracted]);

    // Fallback polling ONLY while the chat is open AND the tab is visible.
    // Realtime (above) delivers new messages instantly via WebSocket — this
    // only covers rare dropped WS events. Interval raised to 120s (was 30s)
    // to further reduce Vercel Serverless invocations.
    // Additionally, a visibilitychange listener re-fetches on tab focus so
    // the user always sees fresh messages when returning to the tab.
    useEffect(() => {
        if (!sessionId || !isOpen || !canReadHistory) return;

        const syncMessages = async () => {
            if (typeof document !== "undefined" && document.hidden) return;
            try {
                // Incremental: ask only for rows newer than the newest confirmed
                // message. Optimistic "temp-" rows are skipped because their
                // timestamps are client-side.
                const confirmed = messagesRef.current.filter((m) => !m.id.startsWith("temp-"));
                const since = confirmed.length ? confirmed[confirmed.length - 1].created_at : "";
                const qs = new URLSearchParams({ session_id: sessionId });
                if (since) qs.set("since", since);
                const res = await fetch(`/api/support/messages?${qs.toString()}`);
                const data = await res.json();
                if (data.messages && Array.isArray(data.messages)) {
                    setMessages((prev) => {
                        if (data.incremental) {
                            const prevIds = new Set(prev.map((m) => m.id));
                            const fresh = data.messages.filter((m: any) => !prevIds.has(m.id));
                            return fresh.length ? [...prev, ...fresh] : prev;
                        }
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
        };

        // Re-sync when the user returns to this tab (free — no extra Vercel call while hidden)
        const onVisibilityChange = () => {
            if (typeof document !== "undefined" && !document.hidden) void syncMessages();
        };
        document.addEventListener("visibilitychange", onVisibilityChange);

        // Periodic safety-net: 120s (was 30s) — Realtime handles the real-time part
        const interval = setInterval(syncMessages, 120000);

        return () => {
            clearInterval(interval);
            document.removeEventListener("visibilitychange", onVisibilityChange);
        };
    }, [sessionId, isOpen, canReadHistory]);

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
