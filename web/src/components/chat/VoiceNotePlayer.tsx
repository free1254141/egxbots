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

// Global in-memory cache for audio blob URLs to guarantee instant <5ms playback and deduplicate network calls
const globalAudioBlobCache = new Map<string, string>();
const globalAudioFetchPromises = new Map<string, Promise<string>>();

function fetchAudioBlobUrl(url: string): Promise<string> {
    if (globalAudioBlobCache.has(url)) {
        return Promise.resolve(globalAudioBlobCache.get(url)!);
    }
    if (globalAudioFetchPromises.has(url)) {
        return globalAudioFetchPromises.get(url)!;
    }
    const p = fetch(url)
        .then(res => {
            if (!res.ok) throw new Error("Audio fetch failed: " + res.status);
            return res.blob();
        })
        .then(blob => {
            const blobUrl = URL.createObjectURL(blob);
            globalAudioBlobCache.set(url, blobUrl);
            globalAudioFetchPromises.delete(url);
            return blobUrl;
        })
        .catch(err => {
            globalAudioFetchPromises.delete(url);
            throw err;
        });
    globalAudioFetchPromises.set(url, p);
    return p;
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

    // Clean spoken text for natural Egyptian Arabic TTS synthesis (entire answer up to 3500 chars)
    const spokenOpinion = useMemo(() => {
        if (isUser) return text ? text.trim() : "";
        // For assistant: Always clean the full response text up to 3500 chars so 100% of the answer is spoken!
        return text ? cleanVoiceText(text, 3500) : (spokenText ? cleanVoiceText(spokenText, 3500) : "");
    }, [spokenText, text, isUser]);

    // Initial realistic duration estimate based on Arabic speech cadence (~12 chars per second)
    const initialEstimatedDuration = useMemo(() => {
        if (durationSeconds && durationSeconds > 0) return durationSeconds;
        if (spokenOpinion.length > 0) {
            return Math.max(3, Math.round(spokenOpinion.length / 12));
        }
        return 5;
    }, [durationSeconds, spokenOpinion]);

    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(initialEstimatedDuration);
    const [isTextExpanded, setIsTextExpanded] = useState(false);
    const [isLoadingAudio, setIsLoadingAudio] = useState(false);
    const [cachedBlobUrl, setCachedBlobUrl] = useState<string | null>(() => {
        if (audioUrl && (audioUrl.startsWith("blob:") || audioUrl.startsWith("data:"))) {
            return audioUrl;
        }
        return null;
    });

    const audioRef = useRef<HTMLAudioElement | null>(null);

    // Determine target audio URL
    const rawAudioTarget = useMemo(() => {
        if (audioUrl) return audioUrl;
        if (!isUser && spokenOpinion) {
            return `/api/voice/tts?text=${encodeURIComponent(spokenOpinion)}&voice=ar-EG-ShakirNeural`;
        }
        return undefined;
    }, [audioUrl, isUser, spokenOpinion]);

    // Exact audio duration calculation via Web Audio API (solves WebM Infinity duration bug in Chrome)
    useEffect(() => {
        if (durationSeconds && durationSeconds > 0) {
            setDuration(durationSeconds);
            return;
        }

        const target = cachedBlobUrl || rawAudioTarget;
        if (!target) return;

        let cancelled = false;

        // Fetch buffer and decode exact PCM frames
        fetch(target)
            .then(res => res.arrayBuffer())
            .then(buf => {
                if (cancelled) return null;
                const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
                if (!AudioContextClass) return null;
                const ctx = new AudioContextClass();
                return ctx.decodeAudioData(buf);
            })
            .then(decoded => {
                if (!cancelled && decoded && decoded.duration && isFinite(decoded.duration) && decoded.duration > 0) {
                    setDuration(Math.max(1, Math.round(decoded.duration)));
                }
            })
            .catch(() => {
                // Non-blocking fallback
            });

        return () => {
            cancelled = true;
        };
    }, [rawAudioTarget, cachedBlobUrl, durationSeconds]);

    // Background prefetch with in-memory caching for zero-delay instant replay
    useEffect(() => {
        if (!rawAudioTarget) return;

        if (rawAudioTarget.startsWith("blob:") || rawAudioTarget.startsWith("data:")) {
            setCachedBlobUrl(rawAudioTarget);
            return;
        }

        if (globalAudioBlobCache.has(rawAudioTarget)) {
            setCachedBlobUrl(globalAudioBlobCache.get(rawAudioTarget)!);
            return;
        }

        let isMounted = true;
        fetchAudioBlobUrl(rawAudioTarget)
            .then(blobUrl => {
                if (isMounted) {
                    setCachedBlobUrl(blobUrl);
                }
            })
            .catch(() => {});

        return () => {
            isMounted = false;
        };
    }, [rawAudioTarget]);

    // Setup HTML5 Audio element instance
    useEffect(() => {
        const activeSrc = cachedBlobUrl || rawAudioTarget;
        if (!activeSrc) return;

        const audio = new Audio();
        audio.preload = "auto";
        audio.src = activeSrc;
        audioRef.current = audio;

        const updateExactDuration = () => {
            if (audio.duration && !isNaN(audio.duration) && isFinite(audio.duration) && audio.duration > 0) {
                setDuration(Math.round(audio.duration));
            }
        };

        audio.onloadedmetadata = updateExactDuration;
        audio.ondurationchange = updateExactDuration;
        audio.oncanplaythrough = () => {
            updateExactDuration();
            setIsLoadingAudio(false);
        };
        audio.oncanplay = () => {
            setIsLoadingAudio(false);
        };

        audio.ontimeupdate = () => {
            setCurrentTime(audio.currentTime);
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
            setIsLoadingAudio(true);
            const playPromise = audio.play();
            if (playPromise !== undefined) {
                playPromise
                    .then(() => {
                        setIsPlaying(true);
                        setIsLoadingAudio(false);
                    })
                    .catch(() => {
                        setIsPlaying(false);
                        setIsLoadingAudio(false);
                    });
            }
        }

        return () => {
            audio.onended = null;
            audio.onerror = null;
            audio.pause();
            audio.src = "";
            audioRef.current = null;
        };
    }, [rawAudioTarget, autoPlay, isUser, cachedBlobUrl]);

    const togglePlay = () => {
        if (!audioRef.current) return;
        if (isPlaying) {
            audioRef.current.pause();
            setIsPlaying(false);
        } else {
            setIsLoadingAudio(true);
            audioRef.current.play()
                .then(() => {
                    setIsPlaying(true);
                    setIsLoadingAudio(false);
                })
                .catch(() => {
                    setIsPlaying(false);
                    setIsLoadingAudio(false);
                });
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
                            <Volume2 className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                            <span className="text-amber-300 truncate">رد أرتورو الصوتي 🎙️</span>
                        </>
                    )}
                </div>
                <div className="flex items-center gap-2 shrink-0 text-[10px] sm:text-[11px] font-mono opacity-80">
                    <span>{formatTime(currentTime)}</span>
                    <span>/</span>
                    <span>{formatTime(effectiveMaxDuration)}</span>
                </div>
            </div>

            {/* Audio waveform / player scrubber controls */}
            <div className="flex items-center gap-2 pt-0.5">
                <button
                    type="button"
                    onClick={togglePlay}
                    disabled={isLoadingAudio && !cachedBlobUrl}
                    className={`w-9 h-9 sm:w-10 sm:h-10 rounded-full flex items-center justify-center shrink-0 transition-transform active:scale-95 cursor-pointer shadow-md ${
                        isUser
                            ? "bg-emerald-500 hover:bg-emerald-400 text-black"
                            : "bg-amber-500 hover:bg-amber-400 text-black"
                    }`}
                    title={isPlaying ? "إيقاف مؤقت" : "تشغيل الصوت"}
                >
                    {isLoadingAudio && !cachedBlobUrl ? (
                        <Loader2 className="w-4 h-4 sm:w-5 sm:h-5 animate-spin" />
                    ) : isPlaying ? (
                        <Pause className="w-4 h-4 sm:w-5 sm:h-5 fill-current" />
                    ) : (
                        <Play className="w-4 h-4 sm:w-5 sm:h-5 fill-current ml-0.5" />
                    )}
                </button>

                <div className="flex-1 flex flex-col justify-center gap-1 min-w-0">
                    <input
                        type="range"
                        min="0"
                        max={effectiveMaxDuration}
                        step="0.1"
                        value={currentTime}
                        onChange={handleSeek}
                        className={`w-full h-1.5 rounded-lg appearance-none cursor-pointer bg-white/20 accent-${
                            isUser ? "emerald-400" : "amber-400"
                        }`}
                    />
                </div>
            </div>

            {/* Text Transcript Accordion (Optional expansion) */}
            {text && text.trim() && (
                <div className="pt-1 border-t border-white/5">
                    <button
                        type="button"
                        onClick={() => setIsTextExpanded(!isTextExpanded)}
                        className="flex items-center gap-1 text-[10px] sm:text-[11px] opacity-70 hover:opacity-100 transition-opacity cursor-pointer py-0.5"
                    >
                        <span>{isTextExpanded ? "إخفاء النص" : "عرض النص المكتوب"}</span>
                        {isTextExpanded ? (
                            <ChevronUp className="w-3 h-3" />
                        ) : (
                            <ChevronDown className="w-3 h-3" />
                        )}
                    </button>

                    {isTextExpanded && (
                        <div className="mt-1.5 p-2 rounded-xl bg-black/30 border border-white/10 text-xs sm:text-sm leading-relaxed text-zinc-200 select-text whitespace-pre-wrap max-h-60 overflow-y-auto">
                            {text}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
