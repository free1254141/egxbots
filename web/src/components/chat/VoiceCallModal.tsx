"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import NextImage from "next/image";
import { 
    PhoneOff, 
    Mic, 
    MicOff, 
    Volume2, 
    VolumeX, 
    Loader2, 
    Sparkles, 
    X,
    Send,
    Radio,
    Zap
} from "lucide-react";
import { toast } from "sonner";
import { cleanVoiceText, playConnectionChime } from "@/lib/voice-utils";

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
    isPro = false,
    remainingQuota = 10,
}: VoiceCallModalProps) {
    const [callState, setCallState] = useState<CallState>("connecting");
    const [callDuration, setCallDuration] = useState(0);
    const [isMuted, setIsMuted] = useState(false);
    const [isSpeakerMuted, setIsSpeakerMuted] = useState(false);
    const [transcript, setTranscript] = useState("");
    const [latestSpokenText, setLatestSpokenText] = useState<string | null>(null);
    const [conversationLog, setConversationLog] = useState<Array<{ sender: "user" | "artoro"; text: string; time: string }>>([]);

    // Synchronous refs to prevent React state closure bugs
    const isOpenRef = useRef(isOpen);
    isOpenRef.current = isOpen;

    const callStateRef = useRef<CallState>(callState);
    callStateRef.current = callState;

    const isMutedRef = useRef(isMuted);
    isMutedRef.current = isMuted;

    const isSpeakerMutedRef = useRef(isSpeakerMuted);
    isSpeakerMutedRef.current = isSpeakerMuted;

    const isProcessingRef = useRef(false);
    const recognitionRef = useRef<any>(null);
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const silenceTimerRef = useRef<NodeJS.Timeout | null>(null);
    const durationTimerRef = useRef<NodeJS.Timeout | null>(null);
    const recognitionRestartTimerRef = useRef<NodeJS.Timeout | null>(null);

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

    // Safe stop of active recognition
    const stopListening = useCallback(() => {
        if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
        if (recognitionRestartTimerRef.current) clearTimeout(recognitionRestartTimerRef.current);

        if (recognitionRef.current) {
            try {
                recognitionRef.current.onend = null;
                recognitionRef.current.onerror = null;
                recognitionRef.current.abort();
            } catch {}
            recognitionRef.current = null;
        }
    }, []);

    // Stop speaking immediately (user interrupt)
    const stopSpeaking = useCallback(() => {
        if (audioRef.current) {
            try {
                audioRef.current.pause();
                audioRef.current.currentTime = 0;
                audioRef.current.src = "";
            } catch {}
            audioRef.current = null;
        }
        if (typeof window !== "undefined" && window.speechSynthesis) {
            try {
                window.speechSynthesis.cancel();
            } catch {}
        }
    }, []);

    // Speech Recognition setup (Web Speech API)
    const startListening = useCallback(() => {
        if (!isOpenRef.current) return;
        if (isMutedRef.current || callStateRef.current === "speaking" || isProcessingRef.current) return;

        const SpeechRecognition =
            (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

        if (!SpeechRecognition) {
            toast.error("المتصفح لا يدعم المايكروفون المباشر. يُفضل استخدام متصفح Chrome أو Safari أو Edge.");
            return;
        }

        try {
            stopListening();

            const rec = new SpeechRecognition();
            rec.lang = "ar-EG";
            rec.continuous = true;
            rec.interimResults = true;
            rec.maxAlternatives = 1;

            rec.onstart = () => {
                if (isOpenRef.current && !isMutedRef.current && callStateRef.current !== "speaking" && !isProcessingRef.current) {
                    setCallState("listening");
                }
            };

            rec.onresult = (event: any) => {
                if (!isOpenRef.current || isProcessingRef.current || callStateRef.current === "speaking") return;

                let fullTranscript = "";
                for (let i = 0; i < event.results.length; ++i) {
                    fullTranscript += event.results[i][0].transcript;
                }

                const cleanedTranscript = fullTranscript.trim();
                setTranscript(cleanedTranscript);

                // Voice Activity Detection (VAD): If silence for 1.1s after speaking, trigger send!
                if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
                if (cleanedTranscript.length >= 2) {
                    silenceTimerRef.current = setTimeout(() => {
                        handleVoiceQuery(cleanedTranscript);
                    }, 1100);
                }
            };

            rec.onerror = (event: any) => {
                const errName = event?.error;
                if (errName === "no-speech") {
                    // Normal silence, keep listening
                    return;
                }
                if (errName === "not-allowed" || errName === "service-not-allowed") {
                    toast.error("يرجى إعطاء صلاحية المايكروفون للمتصفح لمتابعة المكالمة");
                } else {
                    console.warn("Speech recognition notice:", errName);
                }
            };

            rec.onend = () => {
                // Safely restart if still in listening mode
                if (
                    isOpenRef.current &&
                    callStateRef.current !== "speaking" &&
                    callStateRef.current !== "processing" &&
                    callStateRef.current !== "ended" &&
                    !isMutedRef.current &&
                    !isProcessingRef.current
                ) {
                    if (recognitionRestartTimerRef.current) clearTimeout(recognitionRestartTimerRef.current);
                    recognitionRestartTimerRef.current = setTimeout(() => {
                        try {
                            if (isOpenRef.current && callStateRef.current !== "speaking") {
                                rec.start();
                            }
                        } catch {}
                    }, 150);
                }
            };

            rec.start();
            recognitionRef.current = rec;
        } catch (err) {
            console.error("Failed to start speech recognition:", err);
        }
    }, [stopListening]);

    // Play synthesized speech using our zero-cost stream /api/voice/tts with progressive playback
    const playSpeech = useCallback(async (fullText: string) => {
        if (!isOpenRef.current) return;
        if (!fullText || isSpeakerMutedRef.current) {
            setCallState("listening");
            startListening();
            return;
        }

        stopSpeaking();
        stopListening();
        setCallState("speaking");

        const spokenSummary = cleanVoiceText(fullText, 170) || "تمام يا فندم، تم تحديث بيانات السهم والتحليل على شاشتك.";
        setLatestSpokenText(spokenSummary);

        const onPlaybackFinished = () => {
            if (isOpenRef.current) {
                setCallState("listening");
                startListening();
            }
        };

        try {
            // Attempt 1: Native HTML5 progressive streaming audio from Edge-TTS
            const ttsUrl = `/api/voice/tts?text=${encodeURIComponent(spokenSummary)}&voice=ar-EG-ShakirNeural`;
            const audio = new Audio();
            audio.preload = "auto";
            audioRef.current = audio;

            audio.onended = () => {
                onPlaybackFinished();
            };

            audio.onerror = () => {
                console.warn("Edge-TTS stream error, falling back to Web Speech Synthesis");
                fallbackToWebSpeech(spokenSummary, onPlaybackFinished);
            };

            audio.src = ttsUrl;
            const playPromise = audio.play();
            if (playPromise !== undefined) {
                await playPromise;
            }
        } catch (err: any) {
            console.warn("Direct audio play prevented or failed, using Web Speech fallback:", err?.message);
            fallbackToWebSpeech(spokenSummary, onPlaybackFinished);
        }
    }, [startListening, stopListening, stopSpeaking]);

    // Fallback: Client-side Web Speech Synthesis (100% reliable, zero network latency)
    const fallbackToWebSpeech = (text: string, onDone: () => void) => {
        if (typeof window === "undefined" || !window.speechSynthesis) {
            onDone();
            return;
        }

        try {
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = "ar-EG";
            utterance.rate = 1.05;

            // Pick an Arabic voice if available in the browser
            const voices = window.speechSynthesis.getVoices();
            const arVoice = voices.find((v) => v.lang.startsWith("ar"));
            if (arVoice) utterance.voice = arVoice;

            utterance.onend = () => {
                onDone();
            };

            utterance.onerror = () => {
                onDone();
            };

            window.speechSynthesis.speak(utterance);
        } catch {
            onDone();
        }
    };

    // User interrupts assistant speaking
    const handleInterrupt = () => {
        stopSpeaking();
        setCallState("listening");
        startListening();
    };

    // Send question through existing official DeepSeek /api/ai-chat pipeline
    const handleVoiceQuery = useCallback(async (queryText: string) => {
        const cleaned = queryText.trim();
        if (!cleaned || isProcessingRef.current || !isOpenRef.current) return;

        isProcessingRef.current = true;
        stopListening();
        stopSpeaking();
        setCallState("processing");

        const nowStr = new Date().toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" });
        setConversationLog((prev) => [...prev, { sender: "user", text: cleaned, time: nowStr }]);
        setTranscript("");

        try {
            console.log("[VoiceCall] Sending query to DeepSeek AI:", cleaned);
            const aiResponse = await onSendMessage(cleaned);
            const replyText = typeof aiResponse === "string" ? aiResponse : (aiResponse?.content || "");

            console.log("[VoiceCall] Received AI reply length:", replyText.length);
            const safeReply = replyText || "عفواً، تم استلام سؤالك وتحديث البيانات في الشات الرئيسي.";

            setConversationLog((prev) => [...prev, { sender: "artoro", text: safeReply, time: nowStr }]);
            await playSpeech(safeReply);
        } catch (err: any) {
            console.error("[VoiceCall] Error executing AI query:", err);
            const failMessage = "عفواً يا فندم، حدث تأخر في الشبكة، برجاء تكرار سؤالك مرة أخرى.";
            setConversationLog((prev) => [...prev, { sender: "artoro", text: failMessage, time: nowStr }]);
            await playSpeech(failMessage);
        } finally {
            isProcessingRef.current = false;
        }
    }, [onSendMessage, playSpeech, stopListening, stopSpeaking]);

    // Initial connection sequence on modal open
    useEffect(() => {
        if (isOpen) {
            setCallState("connecting");
            setCallDuration(0);
            setTranscript("");
            setConversationLog([]);
            setLatestSpokenText(null);
            isProcessingRef.current = false;

            // Unlock audio context and play connection chime immediately
            playConnectionChime();

            // Transition directly to listening after brief connection feedback (400ms)
            const connectTimer = setTimeout(() => {
                if (isOpenRef.current) {
                    setCallState("listening");
                    startListening();
                }
            }, 400);

            return () => {
                clearTimeout(connectTimer);
                stopListening();
                stopSpeaking();
            };
        } else {
            stopListening();
            stopSpeaking();
        }
    }, [isOpen, startListening, stopListening, stopSpeaking]);

    const handleEndCall = () => {
        setCallState("ended");
        stopListening();
        stopSpeaking();
        toast.info("تم إنهاء المكالمة الصوتية");
        setTimeout(() => {
            onClose();
        }, 200);
    };

    const toggleMute = () => {
        if (isMuted) {
            setIsMuted(false);
            isMutedRef.current = false;
            toast.success("تم تشغيل المايكروفون");
            if (callStateRef.current !== "speaking" && !isProcessingRef.current) {
                setCallState("listening");
                startListening();
            }
        } else {
            setIsMuted(true);
            isMutedRef.current = true;
            stopListening();
            setCallState("muted");
            toast.info("تم كتم المايكروفون");
        }
    };

    const toggleSpeaker = () => {
        if (isSpeakerMuted) {
            setIsSpeakerMuted(false);
            isSpeakerMutedRef.current = false;
            if (audioRef.current) audioRef.current.muted = false;
            toast.success("تم تفعيل الصوت");
        } else {
            setIsSpeakerMuted(true);
            isSpeakerMutedRef.current = true;
            if (audioRef.current) audioRef.current.muted = true;
            stopSpeaking();
            toast.info("تم كتم صوت أرتورو");
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[999999] flex items-center justify-center bg-black/90 backdrop-blur-2xl p-2 sm:p-4 animate-in fade-in duration-200">
            <div className="relative w-full max-w-lg h-[94vh] max-h-[760px] flex flex-col justify-between rounded-3xl bg-gradient-to-b from-zinc-900 via-black to-zinc-950 border-2 border-white/20 shadow-[0_0_60px_rgba(245,158,11,0.2)] text-white overflow-hidden">
                
                {/* Header info */}
                <div className="flex items-center justify-between p-3.5 sm:p-4 border-b border-white/10 bg-black/40 shrink-0">
                    <div className="flex items-center gap-2">
                        <span className="flex h-2.5 w-2.5 relative">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                        </span>
                        <span className="text-xs font-black uppercase tracking-wider text-emerald-400">
                            مكالمة صوتية حية
                        </span>
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-bold border border-amber-500/30">
                            {isPro ? "PRO Voice" : "Free Voice"}
                        </span>
                    </div>

                    <div className="flex items-center gap-3">
                        <span className="font-mono text-sm font-bold text-zinc-300">
                            {formatDuration(callDuration)}
                        </span>
                        <button
                            type="button"
                            onClick={handleEndCall}
                            className="p-1.5 rounded-full hover:bg-white/10 text-zinc-400 hover:text-white transition cursor-pointer"
                            aria-label="إغلاق المكالمة"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                {/* Central Visualizer & Avatar Area */}
                <div className="flex-1 flex flex-col items-center justify-center p-4 sm:p-6 text-center space-y-4 sm:space-y-6 relative overflow-hidden min-h-0">
                    
                    {/* Glowing Audio Pulse Waves */}
                    <div className="relative flex items-center justify-center shrink-0">
                        {callState === "speaking" && (
                            <div className="absolute -inset-10 rounded-full bg-amber-500/25 animate-ping opacity-60"></div>
                        )}
                        {callState === "listening" && (
                            <div className="absolute -inset-8 rounded-full bg-emerald-500/25 animate-pulse"></div>
                        )}
                        {callState === "processing" && (
                            <div className="absolute -inset-8 rounded-full bg-indigo-500/30 animate-spin duration-1000"></div>
                        )}

                        <div className={`relative w-24 h-24 sm:w-32 sm:h-32 rounded-full border-4 p-1 shadow-2xl transition-all duration-300 ${
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
                    <div className="space-y-2 max-w-sm w-full">
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
                                    <span className="text-emerald-300">أرتورو يستمع إليك... تحدث الآن</span>
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

                        {/* Live User Speech Transcript with Instant Send Button */}
                        {transcript && (
                            <div className="p-3 rounded-2xl bg-emerald-950/40 border border-emerald-500/30 text-xs sm:text-sm text-emerald-300 font-medium animate-in fade-in flex items-center justify-between gap-2 text-right">
                                <span className="flex-1 truncate">&quot;{transcript}&quot;</span>
                                <button
                                    type="button"
                                    onClick={() => handleVoiceQuery(transcript)}
                                    className="shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black text-xs font-black shadow-md cursor-pointer transition active:scale-95"
                                    title="إرسال السؤال فوراً دون انتظار الصمت"
                                >
                                    <Zap className="w-3.5 h-3.5" />
                                    <span>إرسال</span>
                                </button>
                            </div>
                        )}

                        {/* Speaking Mode: Stop / Interrupt Button */}
                        {callState === "speaking" && (
                            <div className="pt-1">
                                <button
                                    type="button"
                                    onClick={handleInterrupt}
                                    className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full bg-white/10 hover:bg-white/20 border border-white/20 text-xs text-zinc-200 hover:text-white transition active:scale-95 cursor-pointer shadow-sm"
                                    title="إيقاف صوت أرتورو وبدء الحديث"
                                >
                                    <Radio className="w-3.5 h-3.5 text-amber-400" />
                                    <span>تكلم الآن / مقاطعة الصوت ✋</span>
                                </button>
                            </div>
                        )}
                    </div>

                    {/* Quick Suggestions Pills when Listening */}
                    {callState === "listening" && !transcript && (
                        <div className="flex flex-wrap justify-center gap-1.5 pt-1 max-w-sm">
                            {["حلل سهم فوري", "أقوى أسهم التجميع", "ملخص السوق اليوم", "قارن التجاري وهيرميس"].map((sug) => (
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

                    {/* Recent Message Snippet Log */}
                    {conversationLog.length > 0 && (
                        <div className="w-full max-h-32 sm:max-h-40 overflow-y-auto rounded-2xl bg-white/5 border border-white/10 p-2.5 text-right text-xs space-y-2 mt-2">
                            {conversationLog.slice(-3).map((item, idx) => (
                                <div key={idx} className={`p-2 rounded-xl ${item.sender === "user" ? "bg-emerald-950/30 text-emerald-300 border border-emerald-500/20" : "bg-zinc-800/60 text-zinc-200 border border-white/10"}`}>
                                    <div className="flex items-center justify-between text-[10px] text-zinc-400 mb-0.5">
                                        <span>{item.sender === "user" ? "👤 أنت" : "🤖 أرتورو"}</span>
                                        <span>{item.time}</span>
                                    </div>
                                    <p className="line-clamp-3 leading-relaxed">{item.text}</p>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Bottom Controls Bar */}
                <div className="p-4 sm:p-5 border-t border-white/10 bg-black/60 flex items-center justify-around shrink-0">
                    
                    {/* Mute Button */}
                    <button
                        type="button"
                        onClick={toggleMute}
                        className={`p-3.5 sm:p-4 rounded-full border-2 transition-all shadow-lg active:scale-95 cursor-pointer ${
                            isMuted 
                                ? "bg-rose-500/20 border-rose-500 text-rose-400" 
                                : "bg-white/10 border-white/20 text-white hover:bg-white/20"
                        }`}
                        title={isMuted ? "تشغيل المايك" : "كتم المايك"}
                    >
                        {isMuted ? <MicOff className="w-5 h-5 sm:w-6 sm:h-6" /> : <Mic className="w-5 h-5 sm:w-6 sm:h-6" />}
                    </button>

                    {/* Red Hangup Button */}
                    <button
                        type="button"
                        onClick={handleEndCall}
                        className="p-4 sm:p-5 rounded-full bg-rose-600 hover:bg-rose-500 text-white border-2 border-rose-400 shadow-[0_0_25px_rgba(225,29,72,0.5)] active:scale-95 transition-all cursor-pointer"
                        title="إنهاء المكالمة"
                    >
                        <PhoneOff className="w-6 h-6 sm:w-7 sm:h-7" />
                    </button>

                    {/* Speaker Button */}
                    <button
                        type="button"
                        onClick={toggleSpeaker}
                        className={`p-3.5 sm:p-4 rounded-full border-2 transition-all shadow-lg active:scale-95 cursor-pointer ${
                            isSpeakerMuted 
                                ? "bg-amber-500/20 border-amber-500 text-amber-400" 
                                : "bg-white/10 border-white/20 text-white hover:bg-white/20"
                        }`}
                        title={isSpeakerMuted ? "تشغيل الصوت" : "كتم الصوت"}
                    >
                        {isSpeakerMuted ? <VolumeX className="w-5 h-5 sm:w-6 sm:h-6" /> : <Volume2 className="w-5 h-5 sm:w-6 sm:h-6" />}
                    </button>
                </div>
            </div>
        </div>
    );
}
