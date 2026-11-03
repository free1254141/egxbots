"use client";

import React, { useState, useRef, useEffect } from "react";
import { Play, Pause, Volume2, Mic, Bot, ChevronDown, ChevronUp } from "lucide-react";
import { cleanVoiceText, extractVoiceAnalysisSpeech } from "@/lib/voice-utils";

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
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(durationSeconds || 0);
    const [isTextExpanded, setIsTextExpanded] = useState(false);
    const audioRef = useRef<HTMLAudioElement | null>(null);

    // Spoken opinion for voice synthesis
    const spokenOpinion = spokenText || (role === "assistant" && text ? extractVoiceAnalysisSpeech(text) : "");

    // Resolved audio source
    const resolvedAudioSrc = audioUrl || (
        role === "assistant" && spokenOpinion
            ? `/api/voice/tts?text=${encodeURIComponent(cleanVoiceText(spokenOpinion, 250))}&voice=ar-EG-ShakirNeural`
            : undefined
    );

    useEffect(() => {
        if (!resolvedAudioSrc) return;

        const audio = new Audio();
        audio.preload = "metadata";
        audio.src = resolvedAudioSrc;
        audioRef.current = audio;

        audio.onloadedmetadata = () => {
            if (audio.duration && !isNaN(audio.duration) && isFinite(audio.duration)) {
                setDuration(Math.round(audio.duration));
            }
        };

        audio.ontimeupdate = () => {
            setCurrentTime(audio.currentTime);
        };

        audio.onended = () => {
            setIsPlaying(false);
            setCurrentTime(0);
        };

        audio.onerror = () => {
            setIsPlaying(false);
        };

        if (autoPlay && role === "assistant") {
            const playPromise = audio.play();
            if (playPromise !== undefined) {
                playPromise
                    .then(() => setIsPlaying(true))
                    .catch(() => {
                        // Browser autoplay blocked, user can tap play
                        setIsPlaying(false);
                    });
            }
        }

        return () => {
            audio.pause();
            audio.src = "";
            audioRef.current = null;
        };
    }, [resolvedAudioSrc, autoPlay, role]);

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
        const val = Number(e.target.value);
        if (audioRef.current) {
            audioRef.current.currentTime = val;
            setCurrentTime(val);
        }
    };

    const formatTime = (secs: number) => {
        const m = Math.floor(secs / 60);
        const s = Math.floor(secs % 60).toString().padStart(2, "0");
        return `${m}:${s}`;
    };

    const isUser = role === "user";

    return (
        <div className={`flex flex-col space-y-1.5 sm:space-y-2 p-2 sm:p-2.5 md:p-3 rounded-2xl transition-all max-w-full overflow-hidden ${
            isUser 
                ? "bg-emerald-950/60 border border-emerald-500/30 text-emerald-100" 
                : "bg-zinc-900/90 border border-amber-500/30 text-zinc-100 shadow-md"
        }`}>
            {/* Header label */}
            <div className="flex items-center justify-between text-[10px] sm:text-[11px] font-bold opacity-80 pb-1 border-b border-white/10">
                <div className="flex items-center gap-1.5 truncate min-w-0">
                    {isUser ? (
                        <>
                            <Mic className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-emerald-400 shrink-0" />
                            <span className="text-emerald-300 truncate">رسالة صوتية (Voice Note)</span>
                        </>
                    ) : (
                        <>
                            <Volume2 className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-amber-400 shrink-0 animate-pulse" />
                            <span className="text-amber-300 truncate">رد أرتورو الصوتي (Voice Note)</span>
                        </>
                    )}
                </div>
                <span className="font-mono text-[9px] sm:text-[10px] text-zinc-400 shrink-0">
                    {formatTime(currentTime > 0 ? currentTime : duration)}
                </span>
            </div>

            {/* Audio waveform & controls */}
            <div className="flex items-center gap-2 sm:gap-2.5 pt-0.5">
                <button
                    type="button"
                    onClick={togglePlay}
                    className={`grid h-8 w-8 sm:h-9 sm:w-9 shrink-0 place-items-center rounded-full transition active:scale-95 cursor-pointer shadow-md ${
                        isUser 
                            ? "bg-emerald-500 text-black hover:bg-emerald-400" 
                            : "bg-amber-500 text-black hover:bg-amber-400"
                    }`}
                    title={isPlaying ? "إيقاف مؤقت" : "تشغيل الصوت"}
                    aria-label={isPlaying ? "إيقاف مؤقت" : "تشغيل الصوت"}
                >
                    {isPlaying ? <Pause className="w-3.5 h-3.5 sm:w-4 sm:h-4 fill-current" /> : <Play className="w-3.5 h-3.5 sm:w-4 sm:h-4 fill-current ml-0.5" />}
                </button>

                {/* Progress bar / scrubber */}
                <div className="flex-1 flex flex-col justify-center min-w-0">
                    <input
                        type="range"
                        min={0}
                        max={duration || 10}
                        step={0.1}
                        value={currentTime}
                        onChange={handleSeek}
                        className="w-full h-1.5 rounded-lg appearance-none cursor-pointer bg-white/20 accent-amber-400 hover:accent-amber-300 transition"
                    />
                    <div className="flex justify-between items-center text-[9px] text-zinc-400 font-mono mt-0.5 px-0.5">
                        <span>{formatTime(currentTime)}</span>
                        <span>{formatTime(duration)}</span>
                    </div>
                </div>
            </div>

            {/* Expandable text reveal button (WhatsApp style) */}
            {text && (
                <div className="pt-1 border-t border-white/5">
                    <button
                        type="button"
                        onClick={() => setIsTextExpanded(!isTextExpanded)}
                        className="flex items-center justify-between w-full text-[10px] text-zinc-400 hover:text-zinc-200 transition cursor-pointer py-0.5"
                    >
                        <span>{isTextExpanded ? "إخفاء التفاصيل المكتوبة" : (isUser ? "عرض نص الرسالة 📝" : "عرض التحليل المكتوب 📝")}</span>
                        {isTextExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                    </button>

                    {isTextExpanded && (
                        <div className="mt-1 p-2 max-h-48 overflow-y-auto rounded-xl bg-black/40 border border-white/10 text-xs leading-relaxed text-zinc-200 whitespace-pre-wrap animate-in fade-in duration-150">
                            {text}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
