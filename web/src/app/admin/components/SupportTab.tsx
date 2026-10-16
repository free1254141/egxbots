"use client";

import MobileConversation from "./MobileConversation";
import React, { useState, useEffect, useRef, useMemo } from "react";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";
import {
    Send,
    User,
    Bot,
    Loader2,
    MessageSquare,
    Clock,
    Maximize,
    Minimize,
    RefreshCw,
    Search,
    Trash2,
    Crown,
    ExternalLink,
    AlertTriangle,
    UserPlus,
    X,
} from "lucide-react";

type ChatSession = {
    session_id: string;
    user_id?: string;
    user_name: string;
    email?: string;
    whatsapp_number?: string;
    plan?: string;
    last_message: string;
    last_message_time?: string;
    last_at?: string;
    message_count?: number;
};

type SupportMessage = {
    id: string;
    session_id: string;
    sender: "user" | "admin";
    content: string;
    user_name: string;
    created_at: string;
};

export default function SupportTab() {
    const [sessions, setSessions] = useState<ChatSession[]>([]);
    const [loadingSessions, setLoadingSessions] = useState(true);
    const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
    const [messages, setMessages] = useState<SupportMessage[]>([]);
    const [loadingMessages, setLoadingMessages] = useState(false);
    const [input, setInput] = useState("");
    const [replying, setReplying] = useState(false);
    const [mobilePane, setMobilePane] = useState<"sessions" | "conversation">("sessions");
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
    const [deletingMessageId, setDeletingMessageId] = useState<string | null>(null);
    const [showNewChatModal, setShowNewChatModal] = useState(false);
    const [userSearchQuery, setUserSearchQuery] = useState("");
    const [userSearchResults, setUserSearchResults] = useState<any[]>([]);
    const [searchingUsers, setSearchingUsers] = useState(false);
    const searchDebounceTimer = useRef<NodeJS.Timeout | null>(null);

    // Helpers for user information resolution
    const getUserDisplayName = (u: any) => {
        return u.display_name || u.username || u.full_name || (u.email ? u.email.split("@")[0] : `عميل (${u.id.slice(0, 8)})`);
    };

    const isUserPro = (u: any) => {
        const subPlan = u.subscription?.plan_id?.toLowerCase() || "";
        const subActive = u.subscription?.status === "active";
        if (subActive && ["pro", "lifetime", "pro_lifetime"].includes(subPlan)) return true;
        if (String(u.plan || "").toLowerCase().includes("pro")) return true;
        return Boolean(u.is_pro);
    };

    const formatWhatsAppLink = (num?: string) => {
        if (!num) return "";
        const digits = num.replace(/\D/g, "");
        if (!digits) return "";
        const normalized = digits.startsWith("20") ? digits : digits.startsWith("0") ? `2${digits}` : `20${digits}`;
        return `https://wa.me/${normalized}`;
    };

    const fetchUsersForChat = async (q = "") => {
        try {
            setSearchingUsers(true);
            const res = await fetch(`/api/admin/users?search=${encodeURIComponent(q)}&page_size=25`);
            const data = await res.json();
            if (data.users && Array.isArray(data.users)) {
                setUserSearchResults(data.users);
            }
        } catch (err) {
            console.error("Error searching users:", err);
        } finally {
            setSearchingUsers(false);
        }
    };

    const handleUserSearchInputChange = (val: string) => {
        setUserSearchQuery(val);
        if (searchDebounceTimer.current) {
            clearTimeout(searchDebounceTimer.current);
        }
        searchDebounceTimer.current = setTimeout(() => {
            void fetchUsersForChat(val);
        }, 300);
    };

    const handleSelectUserForChat = (u: any) => {
        const displayName = getUserDisplayName(u);
        const proStatus = isUserPro(u);
        const existing = sessions.find((s) => s.session_id === u.id);
        if (existing) {
            setSelectedSessionId(u.id);
        } else {
            const draftSession: ChatSession = {
                session_id: u.id,
                user_id: u.id,
                user_name: displayName,
                email: u.email,
                whatsapp_number: u.whatsapp_number,
                plan: proStatus ? "PRO" : (u.plan || "FREE"),
                last_message: "محادثة جديدة لم تبدأ بعد",
                last_message_time: new Date().toISOString(),
                last_at: new Date().toISOString(),
                message_count: 0
            };
            setSessions((prev) => [draftSession, ...prev]);
            setSelectedSessionId(u.id);
        }
        setMobilePane("conversation");
        setShowNewChatModal(false);
    };

    const messagesContainerRef = useRef<HTMLDivElement>(null);
    const supabase = useMemo(() => createSupabaseBrowserClient(), []);

    // Format ISO dates safely to prevent "Invalid Date"
    const formatTimeOnly = (iso?: string) => {
        if (!iso) return "";
        const d = new Date(iso);
        if (isNaN(d.getTime())) return "";
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    };

    const formatFullDateTime = (iso?: string) => {
        if (!iso) return "";
        const d = new Date(iso);
        if (isNaN(d.getTime())) return "";
        return `${d.toLocaleDateString([], { month: "numeric", day: "numeric" })} ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
    };

    // Scroll to bottom when messages load/change
    useEffect(() => {
        const container = messagesContainerRef.current;
        if (container) {
            container.scrollTop = container.scrollHeight;
        }
    }, [messages]);

    // Fetch chat sessions list
    const fetchSessions = async () => {
        try {
            setLoadingSessions(true);
            const res = await fetch("/api/admin/support/chats");
            const data = await res.json();
            if (data.chats && Array.isArray(data.chats)) {
                setSessions(data.chats);
            }
        } catch (err) {
            console.error("Error fetching support chats:", err);
        } finally {
            setLoadingSessions(false);
        }
    };

    useEffect(() => {
        void fetchSessions();
    }, []);

    // Load messages when a session is selected
    useEffect(() => {
        if (!selectedSessionId) {
            setMessages([]);
            return;
        }

        const fetchMessages = async () => {
            try {
                setLoadingMessages(true);
                const res = await fetch(`/api/admin/support/messages?session_id=${selectedSessionId}`);
                const data = await res.json();
                if (data.messages && Array.isArray(data.messages)) {
                    setMessages(data.messages);
                }
            } catch (err) {
                console.error("Error fetching session messages:", err);
            } finally {
                setLoadingMessages(false);
            }
        };

        void fetchMessages();

        // Subscribe to messages in this session in real-time (WebSockets)
        const channel = supabase
            .channel(`admin-session-ws-${selectedSessionId}`)
            .on(
                "postgres_changes",
                {
                    event: "*",
                    schema: "public",
                    table: "support_messages",
                    filter: `session_id=eq.${selectedSessionId}`
                },
                (payload: any) => {
                    if (payload.eventType === "DELETE") {
                        const delId = payload.old?.id;
                        if (delId) {
                            setMessages((prev) => prev.filter((m) => m.id !== delId));
                        } else {
                            void fetchMessages();
                        }
                        return;
                    }

                    if (payload.eventType === "INSERT") {
                        const newMsg = payload.new as SupportMessage;
                        setMessages((prev) => {
                            if (prev.some((m) => m.id === newMsg.id)) return prev;
                            const tempIndex = prev.findIndex(
                                (m) => m.id.startsWith("temp-") && m.content === newMsg.content && m.sender === newMsg.sender
                            );
                            if (tempIndex > -1) {
                                const list = [...prev];
                                list[tempIndex] = newMsg;
                                return list;
                            }
                            return [...prev, newMsg];
                        });
                    }
                }
            )
            .subscribe();

        return () => {
            void supabase.removeChannel(channel);
        };
    }, [selectedSessionId, supabase]);

    // Subscribe to all new message inserts to update the session list dynamically (WebSockets)
    useEffect(() => {
        const listChannel = supabase
            .channel("admin-support-list-ws")
            .on(
                "postgres_changes",
                {
                    event: "*",
                    schema: "public",
                    table: "support_messages"
                },
                (payload: any) => {
                    if (payload.eventType === "DELETE") {
                        void fetchSessions();
                        return;
                    }

                    if (payload.eventType === "INSERT") {
                        const newMsg = payload.new as SupportMessage;
                        setSessions((prev) => {
                            const existingIndex = prev.findIndex((s) => s.session_id === newMsg.session_id);
                            const prevItem = existingIndex > -1 ? prev[existingIndex] : null;
                            const updatedSession: ChatSession = {
                                session_id: newMsg.session_id,
                                user_id: prevItem?.user_id || (newMsg as any).user_id,
                                user_name: (newMsg.sender === "user" && newMsg.user_name) ? newMsg.user_name : (prevItem?.user_name || "عميل"),
                                email: prevItem?.email,
                                whatsapp_number: prevItem?.whatsapp_number,
                                plan: prevItem?.plan,
                                last_message: newMsg.content,
                                last_message_time: newMsg.created_at,
                                last_at: newMsg.created_at,
                                message_count: (prevItem?.message_count || 0) + 1
                            };
                            const list = [...prev];
                            if (existingIndex > -1) {
                                list.splice(existingIndex, 1);
                            }
                            return [updatedSession, ...list];
                        });
                    }
                }
            )
            .subscribe();

        return () => {
            void supabase.removeChannel(listChannel);
        };
    }, [supabase]);

    // Live polling for selected session messages every 2s
    useEffect(() => {
        if (!selectedSessionId) return;

        const interval = setInterval(async () => {
            try {
                const res = await fetch(`/api/admin/support/messages?session_id=${selectedSessionId}`);
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
                // silent
            }
        }, 2000);

        return () => clearInterval(interval);
    }, [selectedSessionId]);

    const handleSendReply = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || !selectedSessionId) return;

        const content = input.trim();
        setInput("");
        setReplying(true);

        const tempId = "temp-admin-" + Math.random().toString(36).substring(2) + Date.now().toString(36);
        const optimisticMsg: SupportMessage = {
            id: tempId,
            session_id: selectedSessionId,
            sender: "admin",
            content,
            user_name: "Admin",
            created_at: new Date().toISOString()
        };

        setMessages((prev) => [...prev, optimisticMsg]);

        // Optimistically update the session list in sidebar
        setSessions((prev) => {
            const idx = prev.findIndex((s) => s.session_id === selectedSessionId);
            if (idx === -1) return prev;
            const updated: ChatSession = {
                ...prev[idx],
                last_message: content,
                last_message_time: new Date().toISOString(),
                last_at: new Date().toISOString(),
                message_count: (prev[idx].message_count || 0) + 1
            };
            const list = [...prev];
            list.splice(idx, 1);
            return [updated, ...list];
        });

        try {
            const res = await fetch("/api/admin/support/reply", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    session_id: selectedSessionId,
                    content
                })
            });
            const data = await res.json();
            if (data.ok && data.message) {
                setMessages((prev) =>
                    prev.map((m) => m.id === tempId ? data.message : m)
                );
            }
        } catch (err) {
            console.error("Error sending admin reply:", err);
            setMessages((prev) => prev.filter((m) => m.id !== tempId));
        } finally {
            setReplying(false);
        }
    };

    // Delete entire conversation session
    const handleDeleteSession = async (sessionIdToDelete: string, e?: React.MouseEvent) => {
        if (e) e.stopPropagation();
        const ok = window.confirm(
            "هل أنت متأكد من مسح هذه المحادثة بالكامل من السجلات وقاعدة البيانات؟\n(ستختفي فوراً من لوحة الأدمن ومن واجهة المستخدم)"
        );
        if (!ok) return;

        try {
            setDeletingSessionId(sessionIdToDelete);
            const res = await fetch(`/api/admin/support/chats?session_id=${encodeURIComponent(sessionIdToDelete)}`, {
                method: "DELETE"
            });
            const data = await res.json();
            if (data.ok) {
                setSessions((prev) => prev.filter((s) => s.session_id !== sessionIdToDelete));
                if (selectedSessionId === sessionIdToDelete) {
                    setSelectedSessionId(null);
                    setMessages([]);
                    setMobilePane("sessions");
                }
            } else {
                alert(`فشل الحذف: ${data.detail || "حدث خطأ"}`);
            }
        } catch (err: any) {
            console.error("Error deleting session:", err);
            alert("حدث خطأ أثناء محاولة مسح المحادثة");
        } finally {
            setDeletingSessionId(null);
        }
    };

    // Delete single message
    const handleDeleteMessage = async (messageId: string) => {
        const ok = window.confirm("هل تريد مسح هذه الرسالة نهائياً؟ ستختفي من الطرفين.");
        if (!ok) return;

        try {
            setDeletingMessageId(messageId);
            const res = await fetch(`/api/admin/support/messages?message_id=${encodeURIComponent(messageId)}`, {
                method: "DELETE"
            });
            const data = await res.json();
            if (data.ok) {
                setMessages((prev) => prev.filter((m) => m.id !== messageId));
            } else {
                alert(`فشل مسح الرسالة: ${data.detail || "حدث خطأ"}`);
            }
        } catch (err: any) {
            console.error("Error deleting message:", err);
            alert("حدث خطأ أثناء مسح الرسالة");
        } finally {
            setDeletingMessageId(null);
        }
    };

    // Filter sessions by search query
    const filteredSessions = useMemo(() => {
        if (!searchQuery.trim()) return sessions;
        const q = searchQuery.toLowerCase().trim();
        return sessions.filter((s) =>
            s.user_name.toLowerCase().includes(q) ||
            s.session_id.toLowerCase().includes(q) ||
            (s.email && s.email.toLowerCase().includes(q)) ||
            (s.whatsapp_number && s.whatsapp_number.includes(q)) ||
            (s.last_message && s.last_message.toLowerCase().includes(q))
        );
    }, [sessions, searchQuery]);

    const activeSession = sessions.find((s) => s.session_id === selectedSessionId);

    return (
        <div className={isFullscreen
            ? "fixed inset-0 z-[100] bg-white dark:bg-black flex flex-col overflow-hidden m-0 w-full h-dvh min-w-0"
            : "w-full h-[75dvh] min-h-[480px] md:h-[800px] md:min-h-[650px] border-4 border-black dark:border-white shadow-[8px_8px_0px_rgba(0,0,0,1)] dark:shadow-[8px_8px_0px_rgba(255,255,255,1)] flex flex-col overflow-hidden bg-white dark:bg-zinc-950 text-black dark:text-white"
        }>
            {/* Top Bar matching AI Chatbot Tab */}
            <div className="p-3 md:p-4 border-b-4 border-black dark:border-white flex flex-col sm:flex-row sm:items-center justify-between gap-3 shrink-0 bg-gradient-to-r from-amber-400/20 via-zinc-100 to-amber-500/10 dark:from-amber-950/40 dark:via-zinc-900 dark:to-zinc-900">
                <div className="flex items-center gap-3">
                    <div className="p-2.5 rounded-xl bg-amber-400 text-black border-2 border-black shadow-[2px_2px_0px_#000] shrink-0">
                        <MessageSquare className="w-5 h-5" />
                    </div>
                    <div>
                        <div className="flex items-center gap-2">
                            <h3 className="text-sm md:text-base font-black uppercase tracking-tight text-black dark:text-white">
                                💬 تذاكر ودعم العملاء المباشر (Human Support)
                            </h3>
                            <span className="text-[10px] bg-amber-400 text-black border border-black px-2 py-0.5 rounded-full font-black font-mono">
                                {sessions.length} محادثة
                            </span>
                        </div>
                        <p className="text-[11px] text-zinc-600 dark:text-zinc-400 font-medium">
                            محادثات الدعم الفني المباشر ومزامنة الردود مع تليجرام والموقع
                        </p>
                    </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                    {/* Search Input */}
                    <div className="relative flex-1 sm:w-64">
                        <Search className="w-4 h-4 text-zinc-400 absolute right-3 top-1/2 -translate-y-1/2" />
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            placeholder="بحث بالاسم أو الهاتف أو الجلسة..."
                            className="w-full h-9 rounded-lg border-2 border-black dark:border-zinc-700 bg-white dark:bg-zinc-900 pr-9 pl-3 text-xs text-black dark:text-white placeholder:text-zinc-400 focus:outline-none focus:border-amber-500 transition-colors"
                        />
                    </div>

                    {/* Refresh Button */}
                    <button
                        onClick={() => fetchSessions()}
                        disabled={loadingSessions}
                        className="h-9 w-9 flex items-center justify-center rounded-lg border-2 border-black dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors text-black dark:text-white shadow-[2px_2px_0px_#000] dark:shadow-none"
                        title="تحديث قائمة المحادثات"
                    >
                        <RefreshCw className={`w-4 h-4 ${loadingSessions ? "animate-spin" : ""}`} />
                    </button>

                    {/* Fullscreen Button */}
                    <button
                        onClick={() => setIsFullscreen(!isFullscreen)}
                        className="h-9 w-9 flex items-center justify-center rounded-lg border-2 border-black dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors text-black dark:text-white shadow-[2px_2px_0px_#000] dark:shadow-none"
                        title={isFullscreen ? "تصغير الواجهة" : "تكبير الواجهة بالكامل (Fullscreen)"}
                    >
                        {isFullscreen ? <Minimize className="w-4 h-4" /> : <Maximize className="w-4 h-4" />}
                    </button>
                </div>
            </div>

            {/* Main Area: Sidebar + Conversation */}
            <div className="flex flex-1 min-h-0 min-w-0 overflow-hidden">
                {/* Sidebar: Chat Sessions List */}
                <div
                    data-testid="support-session-list"
                    className="flex lg:flex w-full lg:w-1/3 min-w-0 min-h-0 lg:border-r-4 border-black dark:border-white flex-col h-full bg-zinc-50 dark:bg-zinc-900/40"
                >
                    <div className="p-3 border-b-2 border-zinc-200 dark:border-zinc-800 bg-zinc-100 dark:bg-zinc-900 flex flex-col gap-2">
                        <div className="flex items-center justify-between">
                            <span className="text-[11px] font-black uppercase tracking-wider text-zinc-600 dark:text-zinc-400">
                                قائمة تذاكر ومحادثات العملاء ({filteredSessions.length})
                            </span>
                        </div>
                        <button
                            type="button"
                            onClick={() => { setShowNewChatModal(true); void fetchUsersForChat(); }}
                            className="w-full py-2 px-3 bg-amber-400 hover:bg-amber-300 text-black font-black text-xs rounded-lg border-2 border-black flex items-center justify-center gap-1.5 shadow-[2px_2px_0px_#000] active:translate-y-0.5 active:shadow-none transition-all"
                        >
                            <UserPlus className="w-4 h-4" />
                            <span>+ بدء محادثة مع عميل جديد</span>
                        </button>
                    </div>

                    <div className="flex-1 overflow-y-auto divide-y divide-zinc-200 dark:divide-zinc-800 custom-scrollbar">
                        {loadingSessions && sessions.length === 0 ? (
                            <div className="flex flex-col items-center justify-center p-12 text-zinc-400">
                                <Loader2 className="h-6 w-6 animate-spin mb-2" />
                                <span className="text-xs font-bold">جاري تحميل المحادثات...</span>
                            </div>
                        ) : filteredSessions.length === 0 ? (
                            <div className="p-8 text-center text-zinc-400 dark:text-zinc-500 font-bold text-xs space-y-2">
                                <MessageSquare className="h-8 w-8 mx-auto text-zinc-300 dark:text-zinc-700" />
                                <p>{searchQuery ? "لا توجد نتائج مطابقة للبحث." : "لا توجد أي محادثات دعم نشطة حالياً."}</p>
                            </div>
                        ) : (
                            filteredSessions.map((sess) => {
                                const isSelected = selectedSessionId === sess.session_id;
                                const isDeleting = deletingSessionId === sess.session_id;
                                const msgTime = formatTimeOnly(sess.last_message_time || sess.last_at);

                                return (
                                    <div
                                        key={sess.session_id}
                                        className={`group relative flex items-center transition-all ${
                                            isSelected
                                                ? "bg-amber-100/70 dark:bg-amber-950/40 border-r-4 border-amber-500"
                                                : "hover:bg-zinc-100 dark:hover:bg-zinc-800/50"
                                        }`}
                                    >
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setSelectedSessionId(sess.session_id);
                                                setMobilePane("conversation");
                                            }}
                                            className="w-full text-right p-3.5 flex flex-col gap-1.5 min-w-0"
                                        >
                                            <div className="flex items-center justify-between gap-2">
                                                <div className="flex items-center gap-2 min-w-0">
                                                    <div className="h-7 w-7 rounded-lg bg-amber-400 border border-black text-black font-black text-xs flex items-center justify-center shrink-0">
                                                        {sess.plan?.toLowerCase().includes("pro") ? (
                                                            <Crown className="w-3.5 h-3.5 fill-black" />
                                                        ) : (
                                                            sess.user_name.slice(0, 1).toUpperCase()
                                                        )}
                                                    </div>
                                                    <span className="font-black text-xs text-black dark:text-white truncate">
                                                        {sess.user_name}
                                                    </span>
                                                </div>
                                                {msgTime && (
                                                    <span className="text-[10px] text-zinc-400 dark:text-zinc-500 flex items-center gap-1 font-mono shrink-0">
                                                        <Clock className="h-3 w-3" />
                                                        {msgTime}
                                                    </span>
                                                )}
                                            </div>

                                            {/* Details & Last message */}
                                            <div className="flex items-center gap-2 text-[10px] text-zinc-500 dark:text-zinc-400 font-mono">
                                                {sess.whatsapp_number && (
                                                    <span className="text-emerald-700 dark:text-emerald-400 font-bold">
                                                        📱 {sess.whatsapp_number}
                                                    </span>
                                                )}
                                                {sess.email && !sess.whatsapp_number && (
                                                    <span className="truncate max-w-[140px]">{sess.email}</span>
                                                )}
                                            </div>

                                            <p className="text-[11px] text-zinc-600 dark:text-zinc-300 truncate max-w-full font-sans leading-snug">
                                                {sess.last_message || "—"}
                                            </p>
                                        </button>

                                        {/* Quick Delete Session Button */}
                                        <button
                                            type="button"
                                            onClick={(e) => handleDeleteSession(sess.session_id, e)}
                                            disabled={isDeleting}
                                            title="مسح هذه المحادثة بالكامل من السجلات وقاعدة البيانات"
                                            className="opacity-0 group-hover:opacity-100 focus:opacity-100 p-2 ml-2 mr-1 rounded-lg hover:bg-red-500 hover:text-white text-zinc-400 transition-all shrink-0"
                                        >
                                            {isDeleting ? (
                                                <Loader2 className="w-4 h-4 animate-spin text-red-500" />
                                            ) : (
                                                <Trash2 className="w-4 h-4" />
                                            )}
                                        </button>
                                    </div>
                                );
                            })
                        )}
                    </div>
                </div>

                {/* Conversation Pane */}
                <MobileConversation
                    open={mobilePane === "conversation"}
                    onClose={() => setMobilePane("sessions")}
                    title={activeSession?.user_name || "محادثة الدعم"}
                    closeLabel="رجوع لمحادثات الدعم"
                    testId="support-conversation"
                    className="flex-1 min-w-0 min-h-0 flex-col h-full bg-white dark:bg-zinc-950"
                >
                    {selectedSessionId ? (
                        <>
                            {/* Session Header */}
                            <div className="p-3.5 sm:p-4 border-b-2 border-zinc-200 dark:border-zinc-800 bg-zinc-100 dark:bg-zinc-900 flex items-center justify-between shrink-0 gap-2">
                                <div className="flex items-center gap-3 min-w-0 [overflow-wrap:anywhere]">
                                    <div className="h-10 w-10 rounded-xl bg-amber-400 border-2 border-black flex items-center justify-center text-black font-black text-sm shrink-0 shadow-[2px_2px_0px_#000]">
                                        {activeSession?.plan?.toLowerCase().includes("pro") ? (
                                            <Crown className="w-5 h-5 fill-black" />
                                        ) : (
                                            <User className="w-5 h-5" />
                                        )}
                                    </div>
                                    <div className="min-w-0">
                                        <div className="flex items-center gap-2">
                                            <span className="font-black text-xs sm:text-sm text-black dark:text-white truncate">
                                                {activeSession?.user_name || "Guest"}
                                            </span>
                                            {activeSession?.plan?.toLowerCase().includes("pro") && (
                                                <span className="px-1.5 py-0.5 bg-black text-amber-300 text-[9px] font-black rounded">
                                                    VIP PRO
                                                </span>
                                            )}
                                        </div>
                                        <div className="flex flex-wrap items-center gap-2 text-[10px] text-zinc-500 font-mono mt-0.5">
                                            <span>Session: {selectedSessionId}</span>
                                            {activeSession?.whatsapp_number && formatWhatsAppLink(activeSession.whatsapp_number) && (
                                                <a
                                                    href={formatWhatsAppLink(activeSession.whatsapp_number)}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-bold hover:underline"
                                                >
                                                    واتساب: {activeSession.whatsapp_number}
                                                    <ExternalLink className="w-3 h-3" />
                                                </a>
                                            )}
                                            {activeSession?.email && (
                                                <span>الإيميل: {activeSession.email}</span>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                {/* Delete Conversation Button */}
                                <button
                                    type="button"
                                    onClick={() => handleDeleteSession(selectedSessionId)}
                                    disabled={deletingSessionId === selectedSessionId}
                                    className="px-3 py-1.5 rounded-lg border-2 border-red-600 bg-red-50 hover:bg-red-600 text-red-600 hover:text-white font-bold text-xs flex items-center gap-1.5 transition-colors shrink-0 shadow-xs"
                                    title="مسح هذه المحادثة بالكامل من السجلات وقاعدة البيانات"
                                >
                                    {deletingSessionId === selectedSessionId ? (
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                        <Trash2 className="w-4 h-4" />
                                    )}
                                    <span className="hidden sm:inline">مسح السجل بالكامل</span>
                                </button>
                            </div>

                            {/* Messages Area */}
                            <div
                                ref={messagesContainerRef}
                                className="flex-1 min-h-0 min-w-0 overflow-y-auto p-4 sm:p-6 space-y-4 custom-scrollbar bg-zinc-50/50 dark:bg-zinc-950 font-sans"
                            >
                                {loadingMessages && messages.length === 0 ? (
                                    <div className="flex flex-col items-center justify-center h-full text-zinc-400">
                                        <Loader2 className="h-8 w-8 animate-spin mb-2" />
                                        <span className="text-xs font-bold">جاري تحميل رسائل المحادثة...</span>
                                    </div>
                                ) : messages.length === 0 ? (
                                    <div className="flex flex-col items-center justify-center h-full text-zinc-400 space-y-3 p-6 text-center">
                                        <div className="h-12 w-12 rounded-2xl bg-amber-400 border-2 border-black flex items-center justify-center text-black shadow-[2px_2px_0px_#000]">
                                            <Crown className="w-6 h-6 fill-amber-200" />
                                        </div>
                                        <div className="space-y-1 max-w-sm">
                                            <h4 className="font-black text-sm text-black dark:text-white">
                                                بدء محادثة جديدة مع: {activeSession?.user_name}
                                            </h4>
                                            <p className="text-[11px] text-zinc-500 leading-relaxed">
                                                اكتب رسالتك بالأسفل واضغط <b>إرسال الرد</b>. ستصل للعميل فوراً في شات الدعم بحسابه مع إشعار بالرسائل الجديدة.
                                            </p>
                                        </div>
                                        {activeSession?.whatsapp_number && formatWhatsAppLink(activeSession.whatsapp_number) && (
                                            <a
                                                href={formatWhatsAppLink(activeSession.whatsapp_number)}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-white font-bold text-xs shadow-[2px_2px_0px_#000] transition-colors"
                                            >
                                                <span>أو راسله على واتساب مباشرة ({activeSession.whatsapp_number})</span>
                                                <ExternalLink className="w-3.5 h-3.5" />
                                            </a>
                                        )}
                                    </div>
                                ) : (
                                    messages.map((msg) => {
                                        const isDeletingThis = deletingMessageId === msg.id;
                                        const formattedDate = formatFullDateTime(msg.created_at);

                                        return (
                                            <div
                                                key={msg.id}
                                                className={`group/msg flex gap-3 ${msg.sender === "admin" ? "flex-row-reverse" : "flex-row"}`}
                                            >
                                                <div
                                                    className={`
                                                        h-8 w-8 rounded-xl border-2 border-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_#000]
                                                        ${msg.sender === "admin"
                                                            ? "bg-amber-400 text-black border-black"
                                                            : "bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 border-zinc-400 dark:border-zinc-700"
                                                        }
                                                    `}
                                                >
                                                    {msg.sender === "admin" ? (
                                                        <Crown className="h-4 w-4 fill-amber-900" />
                                                    ) : (
                                                        <User className="h-4 w-4" />
                                                    )}
                                                </div>

                                                <div
                                                    className={`
                                                        relative min-w-0 max-w-[calc(100%_-_48px)] sm:max-w-[75%] [overflow-wrap:anywhere] p-3.5 rounded-xl border-2 border-black shadow-[3px_3px_0px_rgba(0,0,0,0.15)] dark:shadow-[3px_3px_0px_rgba(255,255,255,0.06)] text-xs leading-relaxed
                                                        ${msg.sender === "admin"
                                                            ? "bg-amber-100 dark:bg-amber-950/40 border-amber-500 text-amber-950 dark:text-amber-100 font-medium"
                                                            : "bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 border-black dark:border-zinc-700"
                                                        }
                                                    `}
                                                >
                                                    <div className="flex items-center justify-between gap-4 mb-1">
                                                        <span className="text-[10px] font-black uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                                                            {msg.sender === "admin" ? "الإدارة (Admin)" : (msg.user_name || "العميل")}
                                                        </span>
                                                        {formattedDate && (
                                                            <span className="text-[9px] text-zinc-400 dark:text-zinc-500 font-mono">
                                                                {formattedDate}
                                                            </span>
                                                        )}
                                                    </div>

                                                    <div className="whitespace-pre-wrap">{msg.content}</div>

                                                    {/* Delete Single Message Button */}
                                                    <button
                                                        type="button"
                                                        onClick={() => handleDeleteMessage(msg.id)}
                                                        disabled={isDeletingThis}
                                                        title="مسح هذه الرسالة نهائياً من قاعدة البيانات والطرفين"
                                                        className="absolute -top-2 left-2 opacity-0 group-hover/msg:opacity-100 focus:opacity-100 p-1 rounded bg-red-600 text-white text-[10px] shadow transition-opacity"
                                                    >
                                                        {isDeletingThis ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                                                    </button>
                                                </div>
                                            </div>
                                        );
                                    })
                                )}
                            </div>

                            {/* Reply Input Form */}
                            <form
                                onSubmit={handleSendReply}
                                className="p-3 sm:p-4 shrink-0 border-t-2 border-zinc-200 dark:border-zinc-800 bg-zinc-100 dark:bg-zinc-900 flex gap-2"
                            >
                                <input
                                    type="text"
                                    value={input}
                                    onChange={(e) => setInput(e.target.value)}
                                    placeholder="Type support reply..."
                                    className="flex-1 min-w-0 h-11 rounded-xl bg-white dark:bg-zinc-950 border-2 border-black dark:border-zinc-700 px-4 text-xs sm:text-sm text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 dark:placeholder:text-zinc-500 focus:border-amber-500 focus:outline-none transition-colors"
                                />
                                <button
                                    type="submit"
                                    disabled={replying || !input.trim()}
                                    aria-label="إرسال رد الدعم"
                                    className="shrink-0 h-11 px-5 rounded-xl bg-amber-400 hover:bg-amber-300 border-2 border-black text-black font-black text-xs sm:text-sm flex items-center justify-center gap-1.5 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-[2px_2px_0px_#000] active:translate-y-0.5 active:shadow-none"
                                >
                                    {replying ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                                    <span className="hidden sm:inline">إرسال الرد</span>
                                </button>
                            </form>
                        </>
                    ) : (
                        <div className="flex-1 flex flex-col items-center justify-center text-zinc-400 dark:text-zinc-500 p-8 space-y-3">
                            <div className="h-16 w-16 rounded-2xl bg-zinc-100 dark:bg-zinc-900 border-2 border-black dark:border-white flex items-center justify-center shadow-[4px_4px_0px_#000]">
                                <MessageSquare
                                    aria-label="إرسال رد الدعم"
                                    className="h-8 w-8 text-amber-500 animate-bounce"
                                />
                            </div>
                            <span className="font-black text-sm uppercase tracking-wider text-black dark:text-white">
                                اختر محادثة من القائمة لبدء الرد ومتابعة العميل
                            </span>
                            <p className="text-xs text-zinc-500 max-w-sm text-center">
                                يمكنك الرد مباشرة من هنا أو من خلال حساب التيليجرام بالرد على الرسالة المحولة إليك
                            </p>
                        </div>
                    )}
                </MobileConversation>
            </div>

            {/* New Chat Modal */}
            {showNewChatModal && (
                <div className="fixed inset-0 z-[120] bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in">
                    <div
                        className="w-full max-w-md bg-white dark:bg-zinc-950 border-4 border-black dark:border-white shadow-[8px_8px_0px_#000] dark:shadow-[8px_8px_0px_rgba(255,255,255,0.2)] rounded-2xl flex flex-col overflow-hidden max-h-[85vh]"
                        dir="rtl"
                    >
                        {/* Header */}
                        <div className="p-4 border-b-4 border-black bg-amber-400 text-black flex items-center justify-between shrink-0">
                            <div className="flex items-center gap-2">
                                <UserPlus className="w-5 h-5" />
                                <h3 className="font-black text-sm uppercase">بدء محادثة جديدة مع عميل</h3>
                            </div>
                            <button
                                type="button"
                                onClick={() => setShowNewChatModal(false)}
                                className="p-1 rounded-lg hover:bg-black/10 transition-colors"
                            >
                                <X className="w-5 h-5 text-black" />
                            </button>
                        </div>

                        {/* Search Input */}
                        <div className="p-3 border-b-2 border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900 shrink-0">
                            <div className="relative">
                                <Search className="w-4 h-4 text-zinc-400 absolute right-3 top-1/2 -translate-y-1/2" />
                                <input
                                    type="text"
                                    value={userSearchQuery}
                                    onChange={(e) => handleUserSearchInputChange(e.target.value)}
                                    placeholder="ابحث بالاسم، الإيميل، أو رقم الهاتف..."
                                    className="w-full h-10 rounded-xl border-2 border-black dark:border-zinc-700 bg-white dark:bg-zinc-950 pr-9 pl-3 text-xs text-black dark:text-white placeholder:text-zinc-400 focus:outline-none focus:border-amber-500"
                                    autoFocus
                                />
                            </div>
                        </div>

                        {/* Users List */}
                        <div className="flex-1 overflow-y-auto p-2 divide-y divide-zinc-100 dark:divide-zinc-800 custom-scrollbar">
                            {searchingUsers ? (
                                <div className="flex flex-col items-center justify-center p-10 text-zinc-400">
                                    <Loader2 className="w-6 h-6 animate-spin mb-2" />
                                    <span className="text-xs font-bold">جاري البحث عن العملاء...</span>
                                </div>
                            ) : userSearchResults.length === 0 ? (
                                <div className="p-8 text-center text-zinc-400 text-xs font-bold">
                                    لا يوجد مستخدمين مطابقين للبحث.
                                </div>
                            ) : (
                                userSearchResults.map((u) => {
                                    const displayName = getUserDisplayName(u);
                                    const isPro = isUserPro(u);

                                    return (
                                        <button
                                            key={u.id}
                                            type="button"
                                            onClick={() => handleSelectUserForChat(u)}
                                            className="w-full text-right p-3 hover:bg-amber-50 dark:hover:bg-zinc-900 rounded-xl flex items-center justify-between gap-3 transition-colors group"
                                        >
                                            <div className="flex items-center gap-2.5 min-w-0">
                                                <div className="h-9 w-9 rounded-xl bg-amber-400 border border-black flex items-center justify-center text-black font-black text-xs shrink-0">
                                                    {isPro ? <Crown className="w-4 h-4 fill-black" /> : <User className="w-4 h-4" />}
                                                </div>
                                                <div className="min-w-0">
                                                    <div className="flex items-center gap-1.5">
                                                        <span className="font-black text-xs text-black dark:text-white truncate">
                                                            {displayName}
                                                        </span>
                                                        {isPro && (
                                                            <span className="px-1.5 py-0.2 bg-black text-amber-300 text-[8px] font-black rounded">
                                                                PRO
                                                            </span>
                                                        )}
                                                    </div>
                                                    <div className="flex items-center gap-2 text-[10px] text-zinc-500 font-mono mt-0.5">
                                                        {u.whatsapp_number && (
                                                            <span className="text-emerald-600 font-bold">📱 {u.whatsapp_number}</span>
                                                        )}
                                                        {u.email && <span className="truncate max-w-[150px]">{u.email}</span>}
                                                    </div>
                                                </div>
                                            </div>

                                            <span className="shrink-0 text-[10px] font-bold px-2.5 py-1 bg-amber-400 text-black border border-black rounded-lg shadow-xs group-hover:bg-amber-300 transition-colors">
                                                بدء المحادثة 💬
                                            </span>
                                        </button>
                                    );
                                })
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
