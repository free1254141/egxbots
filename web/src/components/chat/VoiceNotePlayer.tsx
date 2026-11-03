"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import { Play, Pause, Volume2, Mic, ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import { cleanVoiceText } from "@/lib/voice-utils";

interface VoiceNotePlayerProps {
    role: "user" | "assistant" | "system";
    audioUrl?: string;
    text: string;
    spokenText?: string;
    durationSeconds?: number;
    autoPlay?: boolean;
    tables?: any[];
}

export function VoiceNotePlayer({
    role,
    audioUrl,
    text,
    spokenText,
    durationSeconds,
    autoPlay = false,
}: VoiceNotePlayerProps) {
    const isUser = role === "user";

    // Clean spoken text for natural Egyptian Arabic TTS synthesis (up to 1500 chars)
    const spokenOpinion = useMemo(() => {
        if (spokenText && spokenText.trim()) return spokenText.trim();
        if (isUser) return text ? text.trim() : "";
        return text ? cleanVoiceText(text, 1500) : "";
    }, [spokenText, text, isUser]);

    // Initial realistic duration estimate based on Arabic speech cadence (~12 chars per second)
    const initialEstimatedDuration = useMemo(() => {
        if (durationSeconds && durationSeconds > 0) return durationSeconds;
        if (spokenOpinion.length > 0) {
            return Math.max(5, Math.round(spokenOpinion.length / 12));
        }
        return 10;
    }, [durationSeconds, spokenOpinion]);

    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(initialEstimatedDuration);
    const [isTextExpanded, setIsTextExpanded] = useState(false);
    const [isLoadingAudio, setIsLoadingAudio] = useState(false);
    const [blobAudioUrl, setBlobAudioUrl] = useState<string | null>(null);

    const audioRef = useRef<HTMLAudioElement | null>(null);

    // Determine target audio URL
    const rawAudioTarget = useMemo(() => {
        if (audioUrl) return audioUrl;
        if (!isUser && spokenOpinion) {
            return `/api/voice/tts?text=${encodeURIComponent(cleanVoiceText(spokenOpinion, 1500))}&voice=ar-EG-ShakirNeural`;
        }
        return undefined;
    }, [audioUrl, isUser, spokenOpinion]);

    // Prefetch remote TTS audio into a local Blob URL for exact duration and instant seeking
    useEffect(() => {
        if (!rawAudioTarget) {
            setBlobAudioUrl(null);
            return;
        }

        // If it's already a client Blob or data URL, use it directly
        if (rawAudioTarget.startsWith("blob:") || rawAudioTarget.startsWith("data:")) {
            setBlobAudioUrl(rawAudioTarget);
            return;
        }

        let isMounted = true;
        let createdUrl: string | null = null;
        setIsLoadingAudio(true);

        fetch(rawAudioTarget)
            .then(res => {
                if (!res.ok) throw new Error(`TTS fetch returned status ${res.status}`);
                return res.blob();
            })
            .then(blob => {
                if (!isMounted) return;
                createdUrl = URL.createObjectURL(blob);
                setBlobAudioUrl(createdUrl);
                setIsLoadingAudio(false);
            })
            .catch(err => {
                console.warn("[VoiceNotePlayer] Blob fetch failed, falling back to direct URL:", err);
                if (isMounted) {
                    setBlobAudioUrl(rawAudioTarget);
                    setIsLoadingAudio(false);
                }
            });

        return () => {
            isMounted = false;
            if (createdUrl) {
                URL.revokeObjectURL(createdUrl);
            }
        };
    }, [rawAudioTarget]);

    // Setup Audio instance with finite duration and smooth event listeners
    useEffect(() => {
        if (!blobAudioUrl) return;

        const audio = new Audio();
        audio.preload = "auto";
        audio.src = blobAudioUrl;
        audioRef.current = audio;

        const updateExactDuration = () => {
            if (audio.duration && !isNaN(audio.duration) && isFinite(audio.duration) && audio.duration > 0) {
                setDuration(Math.round(audio.duration));
            }
        };

        audio.onloadedmetadata = updateExactDuration;
        audio.ondurationchange = updateExactDuration;
        audio.oncanplaythrough = updateExactDuration;

        audio.ontimeupdate = () => {
            setCurrentTime(audio.currentTime);
            // Dynamically expand duration if audio surpasses initial estimate
            if (audio.currentTime > duration) {
                setDuration(Math.ceil(audio.currentTime));
            }
        };

        audio.onended = () => {
            setIsPlaying(false);
            setCurrentTime(0);
            if (audioRef.current) {
                audioRef.current.currentTime = 0;
            }
        };

        audio.onerror = () => {
            setIsPlaying(false);
            setIsLoadingAudio(false);
        };

        if (autoPlay && !isUser) {
            const playPromise = audio.play();
            if (playPromise !== undefined) {
                playPromise
                    .then(() => setIsPlaying(true))
                    .catch(() => {
                        // Handled: Autoplay blocked by browser policy without user gesture
                        setIsPlaying(false);
                    });
            }
        }

        return () => {
            audio.pause();
            audio.src = "";
            audioRef.current = null;
        };
    }, [blobAudioUrl, autoPlay, isUser]);

    const togglePlay = () => {
        if (!audioRef.current) return;
        if (isPlaying) {
            audioRef.current.pause();
            setIsPlaying(false);
        } else {
            audioRef.current.play()
                .then(() => setIsPlaying(true))
                .catch(() => setIsPlaying(false));
        }
    };

    const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
        const val = parseFloat(e.target.value);
        setCurrentTime(val);
        if (audioRef.current) {
            audioRef.current.currentTime = val;
        }
    };

    const formatTime = (secs: number) => {
        if (isNaN(secs) || secs < 0) secs = 0;
        const m = Math.floor(secs / 60);
        const s = Math.floor(secs % 60).toString().padStart(2, "0");
        return `${m}:${s}`;
    };

    const effectiveMaxDuration = Math.max(duration || 0, Math.ceil(currentTime || 0), 1);

    return (
        <div className={`flex flex-col space-y-1.5 sm:space-y-2 p-2.5 sm:p-3 rounded-2xl transition-all max-w-full overflow-hidden ${
            isUser 
                ? "bg-emerald-950/70 border border-emerald-500/40 text-emerald-100 shadow-md" 
                : "bg-zinc-900/95 border border-amber-500/40 text-zinc-100 shadow-lg"
        }`}>
            {/* Header label */}
            <div className="flex items-center justify-between text-[11px] sm:text-xs font-bold opacity-90 pb-1.5 border-b border-white/10">
                <div className="flex items-center gap-1.5 truncate min-w-0">
                    {isUser ? (
                        <>
                            <Mic className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                            <span className="text-emerald-300 truncate">رسالة صوتية (Voice Note)</span>
                        </>
                    ) : (
                        <>
                            <Volume2 className="w-3.5 h-3.5 text-amber-400 shrink-0 animate-pulse" />
                            <span className="text-amber-300 truncate">
                                {isLoadingAudio ? "جاري تحضير الرد الصوتي... 🎙️" : "رد أرتورو الصوتي (Voice Note)"}
                            </span>
                        </>
                    )}
                </div>
                <span className="font-mono text-[10px] sm:text-[11px] text-zinc-300 shrink-0">
                    {formatTime(currentTime > 0 ? currentTime : effectiveMaxDuration)}
                </span>
            </div>

            {/* Audio controls & interactive scrubber */}
            <div className="flex items-center gap-2.5 sm:gap-3 pt-0.5">
                <button
                    type="button"
                    onClick={togglePlay}
                    disabled={isLoadingAudio && !audioRef.current}
                    className={`grid h-9 w-9 sm:h-10 sm:w-10 shrink-0 place-items-center rounded-full transition active:scale-95 cursor-pointer shadow-md disabled:opacity-60 ${
                        isUser 
                            ? "bg-emerald-500 text-black hover:bg-emerald-400" 
                            : "bg-amber-500 text-black hover:bg-amber-400"
                    }`}
                    title={isPlaying ? "إيقاف مؤقت" : "تشغيل الصوت"}
                    aria-label={isPlaying ? "إيقاف مؤقت" : "تشغيل الصوت"}
                >
                    {isLoadingAudio ? (
                        <Loader2 className="w-4 h-4 animate-spin text-black" />
                    ) : isPlaying ? (
                        <Pause className="w-4 h-4 fill-current" />
                    ) : (
                        <Play className="w-4 h-4 fill-current ml-0.5" />
                    )}
                </button>

                {/* Progress bar / scrubber with full range and duration accuracy */}
                <div className="flex-1 flex flex-col justify-center min-w-0">
                    <input
                        type="range"
                        min={0}
                        max={effectiveMaxDuration}
                        step={0.1}
                        value={Math.min(currentTime, effectiveMaxDuration)}
                        onChange={handleSeek}
                        className={`w-full h-1.5 sm:h-2 rounded-lg appearance-none cursor-pointer transition ${
                            isUser 
                                ? "bg-white/20 accent-emerald-400 hover:accent-emerald-300" 
                                : "bg-white/20 accent-amber-400 hover:accent-amber-300"
                        }`}
                        title="مرر لتقديم أو تأخير الصوت"
                    />
                    <div className="flex justify-between items-center text-[10px] sm:text-[11px] text-zinc-400 font-mono mt-1 px-0.5">
                        <span className="text-zinc-200">{formatTime(currentTime)}</span>
                        <span>{formatTime(effectiveMaxDuration)}</span>
                    </div>
                </div>
            </div>

            {/* Expandable text reveal button (WhatsApp style) */}
            {text && (
                <div className="pt-1.5 border-t border-white/10">
                    <button
                        type="button"
                        onClick={() => setIsTextExpanded(!isTextExpanded)}
                        className="flex items-center justify-between w-full text-[11px] sm:text-xs text-zinc-300 hover:text-white transition cursor-pointer py-0.5"
                    >
                        <span>{isTextExpanded ? "إخفاء التفاصيل المكتوبة" : (isUser ? "عرض نص الرسالة 📝" : "عرض التحليل المكتوب بالكامل 📝")}</span>
                        {isTextExpanded ? <ChevronUp className="w-3.5 h-3.5 text-zinc-400" /> : <ChevronDown className="w-3.5 h-3.5 text-zinc-400" />}
                    </button>

                    {isTextExpanded && (
                        <div className="mt-1.5 p-2.5 max-h-56 overflow-y-auto rounded-xl bg-black/50 border border-white/10 text-xs sm:text-sm leading-relaxed text-zinc-200 whitespace-pre-wrap animate-in fade-in duration-150">
                            {text}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
