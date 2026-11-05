"use client";

import React, { useState, useEffect, useRef } from "react";
import { Mic, Trash2, Send, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { cleanVoiceTranscript } from "@/lib/voice-utils";

interface VoiceNoteRecorderProps {
    isRecording: boolean;
    onCancel: () => void;
    onSend: (audioBlob: Blob, transcript: string, durationSeconds: number) => Promise<void>;
}

export function VoiceNoteRecorder({
    isRecording,
    onCancel,
    onSend,
}: VoiceNoteRecorderProps) {
    const [duration, setDuration] = useState(0);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [transcript, setTranscript] = useState("");

    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const audioChunksRef = useRef<Blob[]>([]);
    const recognitionRef = useRef<any>(null);
    const transcriptRef = useRef<string>("");
    const timerRef = useRef<NodeJS.Timeout | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const startTimeRef = useRef<number>(0);

    useEffect(() => {
        if (!isRecording) {
            cleanup();
            return;
        }

        startRecording();

        return () => {
            cleanup();
        };
    }, [isRecording]);

    const cleanup = () => {
        if (timerRef.current) clearInterval(timerRef.current);
        startTimeRef.current = 0;
        transcriptRef.current = "";
        if (recognitionRef.current) {
            try {
                recognitionRef.current.onend = null;
                recognitionRef.current.onerror = null;
                recognitionRef.current.abort();
            } catch {}
            recognitionRef.current = null;
        }
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
            try {
                mediaRecorderRef.current.stop();
            } catch {}
            mediaRecorderRef.current = null;
        }
        if (streamRef.current) {
            streamRef.current.getTracks().forEach((track) => track.stop());
            streamRef.current = null;
        }
        audioChunksRef.current = [];
        setDuration(0);
        setTranscript("");
        setIsSubmitting(false);
    };

    const startRecording = async () => {
        setDuration(0);
        setTranscript("");
        transcriptRef.current = "";
        audioChunksRef.current = [];
        startTimeRef.current = Date.now();

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            streamRef.current = stream;

            // 1. Setup MediaRecorder for actual voice audio capture
            const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
                ? "audio/webm;codecs=opus"
                : MediaRecorder.isTypeSupported("audio/mp4")
                ? "audio/mp4"
                : "audio/webm";

            const mediaRecorder = new MediaRecorder(stream, { mimeType });
            mediaRecorderRef.current = mediaRecorder;

            mediaRecorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) {
                    audioChunksRef.current.push(e.data);
                }
            };

            mediaRecorder.start(100);

            // High-precision timer referenced to wall-clock time
            timerRef.current = setInterval(() => {
                if (startTimeRef.current > 0) {
                    setDuration(Math.max(1, Math.round((Date.now() - startTimeRef.current) / 1000)));
                } else {
                    setDuration((prev) => prev + 1);
                }
            }, 500);

            // 2. Setup Background SpeechRecognition for real-time Egyptian Arabic transcription
            const SpeechRecognition =
                (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

            if (SpeechRecognition) {
                try {
                    const rec = new SpeechRecognition();
                    rec.lang = "ar-EG";
                    rec.continuous = true;
                    rec.interimResults = true;
                    rec.maxAlternatives = 1;

                    rec.onresult = (event: any) => {
                        let finalStr = "";
                        let interimStr = "";
                        for (let i = 0; i < event.results.length; i++) {
                            const item = event.results[i];
                            const piece = item[0]?.transcript || "";
                            if (item.isFinal) {
                                finalStr += (finalStr ? " " : "") + piece.trim();
                            } else {
                                interimStr += (interimStr ? " " : "") + piece.trim();
                            }
                        }
                        const combined = (finalStr + " " + interimStr).trim();
                        const cleaned = cleanVoiceTranscript(combined);
                        transcriptRef.current = cleaned;
                        setTranscript(cleaned);
                    };

                    rec.onend = () => {
                        // Keep SpeechRecognition running while recording audio
                        if (startTimeRef.current > 0 && isRecording && recognitionRef.current) {
                            try {
                                rec.start();
                            } catch {}
                        }
                    };

                    rec.onerror = (err: any) => {
                        if (err?.error === "not-allowed") {
                            console.warn("[VoiceNoteRecorder] Mic permission error for speech recognition");
                        }
                    };

                    rec.start();
                    recognitionRef.current = rec;
                } catch (e) {
                    console.warn("Speech recognition not available for voice note, will use server fallback:", e);
                }
            }
        } catch (err: any) {
            console.error("Microphone access error:", err);
            toast.error("يرجى إعطاء صلاحية المايكروفون لتسجيل الفويس نوت");
            onCancel();
        }
    };

    const handleSend = async () => {
        if (isSubmitting) return;
        setIsSubmitting(true);

        const exactDuration = startTimeRef.current > 0
            ? Math.max(1, Math.round((Date.now() - startTimeRef.current) / 1000))
            : Math.max(1, duration);
        const currentTranscript = cleanVoiceTranscript(transcriptRef.current || transcript);

        // Stop recognition
        if (recognitionRef.current) {
            try {
                recognitionRef.current.onend = null;
                recognitionRef.current.abort();
            } catch {}
            recognitionRef.current = null;
        }

        // Stop media recorder and assemble audio blob
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
            mediaRecorderRef.current.onstop = async () => {
                const blob = new Blob(audioChunksRef.current, {
                    type: mediaRecorderRef.current?.mimeType || "audio/webm",
                });
                try {
                    await onSend(blob, currentTranscript, exactDuration);
                } finally {
                    cleanup();
                }
            };
            mediaRecorderRef.current.stop();
        } else {
            const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
            try {
                await onSend(blob, currentTranscript, exactDuration);
            } finally {
                cleanup();
            }
        }
    };

    const formatTime = (secs: number) => {
        const m = Math.floor(secs / 60);
        const s = Math.floor(secs % 60).toString().padStart(2, "0");
        return `${m}:${s}`;
    };

    if (!isRecording) return null;

    return (
        <div className="w-full flex items-center justify-between gap-1 sm:gap-2 px-2 py-1.5 sm:px-3 sm:py-2 rounded-2xl bg-zinc-900/95 backdrop-blur-md border border-emerald-500/50 shadow-lg text-white animate-in slide-in-from-bottom-2 duration-200 min-w-0 max-w-full overflow-hidden">
            {/* Delete / Cancel button */}
            <button
                type="button"
                onClick={onCancel}
                disabled={isSubmitting}
                className="grid h-8 w-8 sm:h-9 sm:w-9 shrink-0 place-items-center rounded-xl bg-white/10 hover:bg-rose-500/20 hover:text-rose-400 text-zinc-300 transition active:scale-95 cursor-pointer"
                title="إلغاء التسجيل"
                aria-label="إلغاء التسجيل"
            >
                <Trash2 className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-rose-400" />
            </button>

            {/* Central Recording Indicator & Timer & Waves & Live Transcript */}
            <div className="flex-1 flex items-center justify-center gap-1.5 sm:gap-2.5 px-1 min-w-0 overflow-hidden">
                <span className="flex h-2.5 w-2.5 shrink-0 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-rose-500"></span>
                </span>
                
                <span className="text-[11px] sm:text-xs font-mono font-bold text-rose-300 shrink-0">
                    {formatTime(duration)}
                </span>
                
                {/* Audio waves animation */}
                <div className="hidden xs:flex items-center gap-0.5 h-3.5 shrink-0">
                    <span className="w-0.5 sm:w-1 h-2 bg-emerald-400 rounded-full animate-bounce"></span>
                    <span className="w-0.5 sm:w-1 h-3.5 bg-emerald-400 rounded-full animate-pulse"></span>
                    <span className="w-0.5 sm:w-1 h-2.5 bg-emerald-400 rounded-full animate-bounce [animation-delay:150ms]"></span>
                    <span className="w-0.5 sm:w-1 h-3.5 bg-emerald-400 rounded-full animate-pulse [animation-delay:300ms]"></span>
                    <span className="w-0.5 sm:w-1 h-2 bg-emerald-400 rounded-full animate-bounce [animation-delay:200ms]"></span>
                </div>

                <span className="text-[10px] sm:text-[11px] text-zinc-300 font-medium truncate flex-1 min-w-0 text-center sm:text-right">
                    {transcript ? `"${transcript}"` : "أرتورو يستمع لصوتك..."}
                </span>
            </div>

            {/* Send Voice Note button */}
            <button
                type="button"
                onClick={handleSend}
                disabled={isSubmitting}
                className="flex items-center gap-1 px-2.5 py-1.5 sm:px-3 sm:py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-emerald-400 hover:from-emerald-400 hover:to-emerald-300 text-black text-xs font-black shadow-md cursor-pointer transition active:scale-95 shrink-0"
                title="إرسال الفويس نوت"
                aria-label="إرسال الفويس نوت"
            >
                {isSubmitting ? (
                    <Loader2 className="w-3.5 h-3.5 sm:w-4 sm:h-4 animate-spin" />
                ) : (
                    <>
                        <span>إرسال</span>
                        <Send className="w-3 h-3 sm:w-3.5 sm:h-3.5" />
                    </>
                )}
            </button>
        </div>
    );
}
