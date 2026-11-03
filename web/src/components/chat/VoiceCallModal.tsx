"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import NextImage from "next/image";
import { 
    Phone, 
    PhoneOff, 
    Mic, 
    MicOff, 
    Volume2, 
    VolumeX, 
    Loader2, 
    Sparkles, 
    X,
    MessageSquare,
    Zap
} from "lucide-react";
import { FormattedChatMessage } from "./FormattedChatMessage";
import { toast } from "sonner";

interface VoiceCallModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSendMessage: (text: string) => Promise<any>;
    lastAssistantMessage?: { role: string; content: string } | null;
    isPro?: boolean;
    remainingQuota?: number;
}

type CallState = "connecting" | "listening" | "processing" | "speaking" | "muted" | "ended";

export function VoiceCallModal({
    isOpen,
    onClose,
    onSendMessage,
    lastAssistantMessage,
    isPro = false,
    remainingQuota = 10,
}: VoiceCallModalProps) {
    const [callState, setCallState] = useState<CallState>("connecting");
    const [callDuration, setCallDuration] = useState(0);
    const [isMuted, setIsMuted] = useState(false);
    const [isSpeakerMuted, setIsSpeakerMuted] = useState(false);
    const [transcript, setTranscript] = useState("");
    const [latestAiReply, setLatestAiReply] = useState<string | null>(null);
    const [conversationLog, setConversationLog] = useState<Array<{ sender: "user" | "artoro"; text: string; time: string }>>([]);

    const recognitionRef = useRef<any>(null);
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const silenceTimerRef = useRef<NodeJS.Timeout | null>(null);
    const durationTimerRef = useRef<NodeJS.Timeout | null>(null);
    const isComponentMounted = useRef(true);
    const isProcessingRef = useRef(false);

    // Call duration counter
    useEffect(() => {
        if (isOpen && callState !== "ended" && callState !== "connecting") {
            durationTimerRef.current = setInterval(() => {
                setCallDuration((prev) => prev + 1);
            }, 1000);
        } else {
            if (durationTimerRef.current) clearInterval(durationTimerRef.current);
        }
        return () => {
            if (durationTimerRef.current) clearInterval(durationTimerRef.current);
        };
    }, [isOpen, callState]);

    const formatDuration = (seconds: number) => {
        const m = Math.floor(seconds / 60).toString().padStart(2, "0");
        const s = (seconds % 60).toString().padStart(2, "0");
        return `${m}:${s}`;
    };

    // Play synthesized speech using our zero-cost /api/voice/tts
    const playSpeech = useCallback(async (text: string) => {
        if (!text || isSpeakerMuted) {
            setCallState("listening");
            startListening();
            return;
        }

        try {
            setCallState("speaking");

            if (audioRef.current) {
                audioRef.current.pause();
                audioRef.current.src = "";
            }

            const response = await fetch("/api/voice/tts", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    text,
                    voice: "ar-EG-ShakirNeural",
                }),
            });

            if (!response.ok) {
                throw new Error("TTS synthesis failed");
            }

            const blob = await response.blob();
            const audioUrl = URL.createObjectURL(blob);
            const audio = new Audio(audioUrl);
            audioRef.current = audio;

            audio.onended = () => {
                URL.revokeObjectURL(audioUrl);
                if (isComponentMounted.current && isOpen) {
                    setCallState("listening");
                    startListening();
                }
            };

            audio.onerror = () => {
                URL.revokeObjectURL(audioUrl);
                if (isComponentMounted.current && isOpen) {
                    setCallState("listening");
                    startListening();
                }
            };

            await audio.play();
        } catch (err) {
            console.error("Audio playback error:", err);
            if (isComponentMounted.current && isOpen) {
                setCallState("listening");
                startListening();
            }
        }
    }, [isOpen, isSpeakerMuted]);

    // Send question through existing official DeepSeek /api/ai-chat pipeline
    const handleVoiceQuery = useCallback(async (queryText: string) => {
        const cleaned = queryText.trim();
        if (!cleaned || isProcessingRef.current) return;

        isProcessingRef.current = true;
        stopListening();
        setCallState("processing");

        const nowStr = new Date().toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" });
        setConversationLog((prev) => [...prev, { sender: "user", text: cleaned, time: nowStr }]);
        setTranscript("");

        try {
            const aiResponse = await onSendMessage(cleaned);
            const replyText = typeof aiResponse === "string" ? aiResponse : (aiResponse?.content || "");

            setLatestAiReply(replyText);
            setConversationLog((prev) => [...prev, { sender: "artoro", text: replyText, time: nowStr }]);

            await playSpeech(replyText);
        } catch (err: any) {
            toast.error("تعذر إكمال الرد الصوتي، يرجى المحاولة مرة أخرى");
            setCallState("listening");
            startListening();
        } finally {
            isProcessingRef.current = false;
        }
    }, [onSendMessage, playSpeech]);

    // Speech Recognition setup (Web Speech API)
    const startListening = useCallback(() => {
        if (isMuted || callState === "speaking" || isProcessingRef.current) return;

        const SpeechRecognition =
            (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

        if (!SpeechRecognition) {
            toast.error("المتصفح لا يدعم المايكروفون المباشر. يُفضل استخدام متصفح Chrome أو Safari أو Edge.");
            return;
        }

        try {
            if (recognitionRef.current) {
                recognitionRef.current.abort();
            }

            const rec = new SpeechRecognition();
            rec.lang = "ar-EG";
            rec.continuous = true;
            rec.interimResults = true;
            rec.maxAlternatives = 1;

            rec.onstart = () => {
                setCallState("listening");
            };

            rec.onresult = (event: any) => {
                let currentTranscript = "";
                for (let i = event.resultIndex; i < event.results.length; ++i) {
                    currentTranscript += event.results[i][0].transcript;
                }

                setTranscript(currentTranscript);

                // Voice Activity Detection (VAD): If silence for 1.3s after speaking, trigger send!
                if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
                if (currentTranscript.trim().length > 2) {
                    silenceTimerRef.current = setTimeout(() => {
                        handleVoiceQuery(currentTranscript);
                    }, 1300);
                }
            };

            rec.onerror = (event: any) => {
                if (event.error !== "no-speech") {
                    console.warn("Speech recognition notice:", event.error);
                }
            };

            rec.onend = () => {
                // Keep listening if call is still active and not speaking or processing
                if (
                    isComponentMounted.current &&
                    isOpen &&
                    (callState as string) !== "speaking" &&
                    callState !== "processing" &&
                    callState !== "ended" &&
                    !isMuted
                ) {
                    try {
                        rec.start();
                    } catch {}
                }
            };

            rec.start();
            recognitionRef.current = rec;
        } catch (err) {
            console.error("Failed to start speech recognition:", err);
        }
    }, [isMuted, callState, isOpen, handleVoiceQuery]);

    const stopListening = useCallback(() => {
        if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
        if (recognitionRef.current) {
            try {
                recognitionRef.current.abort();
            } catch {}
            recognitionRef.current = null;
        }
    }, []);

    // Initial connection sequence on modal open
    useEffect(() => {
        isComponentMounted.current = true;
        if (isOpen) {
            setCallState("connecting");
            setCallDuration(0);
            setTranscript("");
            setConversationLog([]);

            // Simulate call connection chime and welcome greeting
            const connectTimer = setTimeout(() => {
                setCallState("speaking");
                const welcomeMsg = "أهلاً بك يا فندم في محادثة أرتورو الصوتية المباشرة. اسألني عن أي سهم أو اطلب ملخص البورصة وسأجيبك فوراً.";
                playSpeech(welcomeMsg);
            }, 800);

            return () => {
                clearTimeout(connectTimer);
                stopListening();
                if (audioRef.current) {
                    audioRef.current.pause();
                    audioRef.current = null;
                }
            };
        } else {
            stopListening();
            if (audioRef.current) {
                audioRef.current.pause();
                audioRef.current = null;
            }
        }
    }, [isOpen, playSpeech, stopListening]);

    const handleEndCall = () => {
        setCallState("ended");
        stopListening();
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current = null;
        }
        toast.info("تم إنهاء المكالمة الصوتية");
        setTimeout(() => {
            onClose();
        }, 300);
    };

    const toggleMute = () => {
        if (isMuted) {
            setIsMuted(false);
            toast.success("تم تشغيل المايكروفون");
            startListening();
        } else {
            setIsMuted(true);
            stopListening();
            setCallState("muted");
            toast.info("تم كتم المايكروفون");
        }
    };

    const toggleSpeaker = () => {
        if (isSpeakerMuted) {
            setIsSpeakerMuted(false);
            if (audioRef.current) audioRef.current.muted = false;
            toast.success("تم تفعيل الصوت");
        } else {
            setIsSpeakerMuted(true);
            if (audioRef.current) audioRef.current.muted = true;
            toast.info("تم كتم صوت أرتورو");
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[999999] flex items-center justify-center bg-black/90 backdrop-blur-2xl p-2 sm:p-4 animate-in fade-in duration-300">
            <div className="relative w-full max-w-lg h-[92vh] max-h-[750px] flex flex-col justify-between rounded-3xl bg-gradient-to-b from-zinc-900 via-black to-zinc-950 border-2 border-white/20 shadow-[0_0_50px_rgba(245,158,11,0.15)] text-white overflow-hidden">
                
                {/* Header info */}
                <div className="flex items-center justify-between p-4 border-b border-white/10 bg-black/40">
                    <div className="flex items-center gap-2">
                        <span className="flex h-2.5 w-2.5 relative">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                        </span>
                        <span className="text-xs font-black uppercase tracking-wider text-emerald-400">
                            مكالمة حية مع أرتورو
                        </span>
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-bold border border-amber-500/30">
                            PRO Voice
                        </span>
                    </div>

                    <div className="flex items-center gap-3">
                        <span className="font-mono text-sm font-bold text-zinc-300">
                            {formatDuration(callDuration)}
                        </span>
                        <button
                            type="button"
                            onClick={handleEndCall}
                            className="p-1.5 rounded-full hover:bg-white/10 text-zinc-400 hover:text-white transition"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                {/* Central Visualizer & Avatar Area */}
                <div className="flex-1 flex flex-col items-center justify-center p-6 text-center space-y-6 relative overflow-hidden">
                    
                    {/* Glowing Audio Pulse Waves */}
                    <div className="relative flex items-center justify-center">
                        {callState === "speaking" && (
                            <div className="absolute -inset-10 rounded-full bg-amber-500/20 animate-ping opacity-60"></div>
                        )}
                        {callState === "listening" && (
                            <div className="absolute -inset-8 rounded-full bg-emerald-500/20 animate-pulse"></div>
                        )}
                        {callState === "processing" && (
                            <div className="absolute -inset-8 rounded-full bg-indigo-500/25 animate-spin duration-1000"></div>
                        )}

                        <div className={`relative w-28 h-28 sm:w-32 sm:h-32 rounded-full border-4 p-1 shadow-2xl transition-all duration-300 ${
                            callState === "speaking" 
                                ? "border-amber-400 shadow-amber-500/40 scale-105" 
                                : callState === "listening"
                                ? "border-emerald-400 shadow-emerald-500/30"
                                : callState === "processing"
                                ? "border-indigo-400 animate-pulse"
                                : "border-white/20"
                        }`}>
                            <div className="w-full h-full rounded-full overflow-hidden bg-black flex items-center justify-center relative">
                                <NextImage
                                    src="/favicon_io/apple-touch-icon.png"
                                    alt="ARTORO Voice"
                                    width={128}
                                    height={128}
                                    className="w-full h-full object-contain p-2"
                                    priority
                                />
                            </div>
                        </div>
                    </div>

                    {/* Status & Subtitle Indicator */}
                    <div className="space-y-2 max-w-sm">
                        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/10 border border-white/15 text-xs font-black">
                            {callState === "connecting" && (
                                <>
                                    <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-400" />
                                    <span>جاري الاتصال بأرتورو...</span>
                                </>
                            )}
                            {callState === "listening" && (
                                <>
                                    <Mic className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
                                    <span className="text-emerald-300">أرتورو يستمع إليك... تكلم الآن</span>
                                </>
                            )}
                            {callState === "processing" && (
                                <>
                                    <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                                    <span className="text-indigo-300">جاري فحص السهم ومحرك الذكاء...</span>
                                </>
                            )}
                            {callState === "speaking" && (
                                <>
                                    <Volume2 className="w-3.5 h-3.5 text-amber-400 animate-bounce" />
                                    <span className="text-amber-300">أرتورو يتحدث...</span>
                                </>
                            )}
                            {callState === "muted" && (
                                <>
                                    <MicOff className="w-3.5 h-3.5 text-rose-400" />
                                    <span className="text-rose-300">المايكروفون مكتوم</span>
                                </>
                            )}
                        </div>

                        {/* Live User Speech Transcript */}
                        {transcript && (
                            <div className="p-3 rounded-2xl bg-white/5 border border-white/10 text-xs sm:text-sm text-emerald-300 font-medium animate-in fade-in">
                                &quot;{transcript}&quot;
                            </div>
                        )}
                    </div>

                    {/* Quick Suggestions Pills */}
                    {callState === "listening" && !transcript && (
                        <div className="flex flex-wrap justify-center gap-1.5 pt-2">
                            {["حلل سهم فوري", "ملخص السوق اليوم", "أقوى أسهم التجميع", "قارن التجاري وهيرميس"].map((sug) => (
                                <button
                                    key={sug}
                                    type="button"
                                    onClick={() => handleVoiceQuery(sug)}
                                    className="text-[11px] px-3 py-1 rounded-full bg-white/5 hover:bg-white/15 border border-white/10 text-zinc-300 hover:text-white transition cursor-pointer"
                                >
                                    💬 {sug}
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                {/* Bottom Controls Bar */}
                <div className="p-5 border-t border-white/10 bg-black/60 flex items-center justify-around">
                    
                    {/* Mute Button */}
                    <button
                        type="button"
                        onClick={toggleMute}
                        className={`p-4 rounded-full border-2 transition-all shadow-lg active:scale-95 ${
                            isMuted 
                                ? "bg-rose-500/20 border-rose-500 text-rose-400" 
                                : "bg-white/10 border-white/20 text-white hover:bg-white/20"
                        }`}
                        title={isMuted ? "تشغيل المايك" : "كتم المايك"}
                    >
                        {isMuted ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6" />}
                    </button>

                    {/* Red Hangup Button */}
                    <button
                        type="button"
                        onClick={handleEndCall}
                        className="p-5 rounded-full bg-rose-600 hover:bg-rose-500 text-white border-2 border-rose-400 shadow-[0_0_25px_rgba(225,29,72,0.5)] active:scale-95 transition-all cursor-pointer"
                        title="إنهاء المكالمة"
                    >
                        <PhoneOff className="w-7 h-7" />
                    </button>

                    {/* Speaker Button */}
                    <button
                        type="button"
                        onClick={toggleSpeaker}
                        className={`p-4 rounded-full border-2 transition-all shadow-lg active:scale-95 ${
                            isSpeakerMuted 
                                ? "bg-amber-500/20 border-amber-500 text-amber-400" 
                                : "bg-white/10 border-white/20 text-white hover:bg-white/20"
                        }`}
                        title={isSpeakerMuted ? "تشغيل الصوت" : "كتم الصوت"}
                    >
                        {isSpeakerMuted ? <VolumeX className="w-6 h-6" /> : <Volume2 className="w-6 h-6" />}
                    </button>
                </div>
            </div>
        </div>
    );
}
