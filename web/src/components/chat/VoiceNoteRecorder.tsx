"use client";

import React, { useState, useEffect, useRef } from "react";
import { Mic, Trash2, Send, Loader2 } from "lucide-react";
import { toast } from "sonner";

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
    const timerRef = useRef<NodeJS.Timeout | null>(null);
    const streamRef = useRef<MediaStream | null>(null);

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
        audioChunksRef.current = [];

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

            // Timer
            timerRef.current = setInterval(() => {
                setDuration((prev) => prev + 1);
            }, 1000);

            // 2. Setup Background SpeechRecognition for zero-token DeepSeek transcription
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
                        let fullText = "";
                        for (let i = 0; i < event.results.length; i++) {
                            fullText += event.results[i][0].transcript;
                        }
                        setTranscript(fullText.trim());
                    };

                    rec.onerror = () => {};
                    rec.onend = () => {};

                    rec.start();
                    recognitionRef.current = rec;
                } catch (e) {
                    console.warn("Speech recognition not available for voice note, will use audio-only:", e);
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

        const currentDuration = duration;
        const currentTranscript = transcript.trim() || "حلل هذا السهم في البورصة المصرية";

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
                    await onSend(blob, currentTranscript, currentDuration);
                } finally {
                    cleanup();
                }
            };
            mediaRecorderRef.current.stop();
        } else {
            const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
            try {
                await onSend(blob, currentTranscript, currentDuration);
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
        <div className="w-full flex items-center justify-between gap-2 p-2 sm:p-2.5 rounded-2xl bg-zinc-900 border-2 border-emerald-500/50 shadow-lg text-white animate-in slide-in-from-bottom-2 duration-200">
            {/* Delete / Cancel button */}
            <button
                type="button"
                onClick={onCancel}
                disabled={isSubmitting}
                className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/10 hover:bg-rose-500/20 hover:text-rose-400 text-zinc-300 transition active:scale-95 cursor-pointer"
                title="إلغاء التسجيل"
            >
                <Trash2 className="w-4 h-4" />
            </button>

            {/* Central Recording Indicator & Timer */}
            <div className="flex-1 flex items-center justify-center gap-3 px-2">
                <span className="flex h-3 w-3 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-rose-500"></span>
                </span>
                <span className="text-xs font-mono font-bold text-rose-300">
                    {formatTime(duration)}
                </span>
                
                {/* Audio waves animation */}
                <div className="flex items-center gap-0.5 h-4">
                    <span className="w-1 h-2 bg-emerald-400 rounded-full animate-bounce"></span>
                    <span className="w-1 h-4 bg-emerald-400 rounded-full animate-pulse"></span>
                    <span className="w-1 h-3 bg-emerald-400 rounded-full animate-bounce [animation-delay:150ms]"></span>
                    <span className="w-1 h-4 bg-emerald-400 rounded-full animate-pulse [animation-delay:300ms]"></span>
                    <span className="w-1 h-2 bg-emerald-400 rounded-full animate-bounce [animation-delay:200ms]"></span>
                </div>

                <span className="text-[11px] text-zinc-300 font-medium truncate max-w-[140px] sm:max-w-[200px]">
                    {transcript ? `"${transcript}"` : "تسجيل فويس نوت..."}
                </span>
            </div>

            {/* Send Voice Note button */}
            <button
                type="button"
                onClick={handleSend}
                disabled={isSubmitting}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black text-xs font-black shadow-md cursor-pointer transition active:scale-95 shrink-0"
                title="إرسال الفويس نوت"
            >
                {isSubmitting ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                    <>
                        <span>إرسال</span>
                        <Send className="w-3.5 h-3.5" />
                    </>
                )}
            </button>
        </div>
    );
}
