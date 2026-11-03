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







export function primeAudioCache(url?: string, blobUrl?: string) {



    if (!url || !blobUrl) return;



    globalAudioBlobCache.set(url, blobUrl);



}







function getAudioCacheKey(audioUrl?: string, spokenText?: string, isUser = false): string {



    if (audioUrl) return audioUrl;



    // Strict rule: NEVER generate synthetic robot ShakirNeural voice for user messages!



    if (!isUser && spokenText) return `tts:ar-EG-ShakirNeural:${spokenText}`;



    return "";



}







function fetchAudioBlobUrl(audioUrl?: string, spokenText?: string, isUser = false): Promise<string> {



    if (isUser && !audioUrl) {



        return Promise.reject(new Error("No user microphone recording available"));



    }



    const key = getAudioCacheKey(audioUrl, spokenText, isUser);



    if (!key) return Promise.reject(new Error("No audio target"));



    if (globalAudioBlobCache.has(key)) {



        return Promise.resolve(globalAudioBlobCache.get(key)!);



    }



    if (globalAudioFetchPromises.has(key)) {



        return globalAudioFetchPromises.get(key)!;



    }







    const fetchPromise = (async () => {



        let res: Response;



        if (audioUrl) {



            res = await fetch(audioUrl);



        } else {



            // For assistant replies only: robust JSON POST synthesis



            res = await fetch("/api/voice/tts", {



                method: "POST",



                headers: { "Content-Type": "application/json" },



                body: JSON.stringify({



                    text: spokenText,



                    voice: "ar-EG-ShakirNeural",



                    rate: "+12%",



                }),



            });



        }



        if (!res.ok) throw new Error("Audio fetch failed: " + res.status);



        const blob = await res.blob();



        const blobUrl = URL.createObjectURL(blob);



        globalAudioBlobCache.set(key, blobUrl);



        globalAudioFetchPromises.delete(key);



        return blobUrl;



    })().catch(err => {



        globalAudioFetchPromises.delete(key);



        throw err;



    });







    globalAudioFetchPromises.set(key, fetchPromise);



    return fetchPromise;



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







    // Clean spoken text for natural Egyptian Arabic TTS synthesis (100% of answer up to 10,000 chars)



    const spokenOpinion = useMemo(() => {



        if (isUser) return text ? text.trim() : "";



        // For assistant: Always clean the full response text so 100% of the answer is spoken!



        return text ? cleanVoiceText(text, 10000) : (spokenText ? cleanVoiceText(spokenText, 10000) : "");



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



        const initialKey = getAudioCacheKey(audioUrl, spokenOpinion);



        if (initialKey && globalAudioBlobCache.has(initialKey)) {



            return globalAudioBlobCache.get(initialKey)!;



        }



        return null;



    });







    const audioRef = useRef<HTMLAudioElement | null>(null);







    // Audio target key



    const targetKey = useMemo(() => {



        return getAudioCacheKey(audioUrl, spokenOpinion, isUser);



    }, [audioUrl, spokenOpinion, isUser]);







    // Background prefetch with in-memory caching for zero-delay instant replay



    useEffect(() => {



        if (!targetKey) return;







        if (audioUrl && (audioUrl.startsWith("blob:") || audioUrl.startsWith("data:"))) {



            setCachedBlobUrl(audioUrl);



            return;



        }







        if (globalAudioBlobCache.has(targetKey)) {



            setCachedBlobUrl(globalAudioBlobCache.get(targetKey)!);



            return;



        }







        let isMounted = true;



        fetchAudioBlobUrl(audioUrl, spokenOpinion, isUser)



            .then(blobUrl => {



                if (isMounted) {



                    setCachedBlobUrl(blobUrl);



                }



            })



            .catch(() => {});







        return () => {



            isMounted = false;



        };



    }, [targetKey, audioUrl, spokenOpinion]);







    // Exact audio duration calculation via Web Audio API (solves WebM Infinity duration bug in Chrome)



    useEffect(() => {



        if (durationSeconds && durationSeconds > 0) {



            setDuration(durationSeconds);



            return;



        }







        if (!cachedBlobUrl) return;







        let cancelled = false;







        // Fetch buffer and decode exact PCM frames



        fetch(cachedBlobUrl)



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



    }, [cachedBlobUrl, durationSeconds]);
    // Cleanup audio instance only when component actually unmounts
    useEffect(() => {
        return () => {
            if (audioRef.current) {
                audioRef.current.pause();
                audioRef.current = null;
            }
        };
    }, []);

    // Setup and synchronize HTML5 Audio element instance
    useEffect(() => {
        if (!cachedBlobUrl) return;

        let audio = audioRef.current;
        if (!audio) {
            audio = new Audio();
            audio.preload = "auto";
            audioRef.current = audio;
        }

        const updateExactDuration = () => {
            if (audio && audio.duration && !isNaN(audio.duration) && isFinite(audio.duration) && audio.duration > 0) {
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
            setDuration(prev => (audio.currentTime > prev ? Math.ceil(audio.currentTime) : prev));
        };

        audio.onended = () => {
            setIsPlaying(false);
            setCurrentTime(0);
        };

        audio.onerror = () => {
            setIsPlaying(false);
            setIsLoadingAudio(false);
        };

        if (audio.src !== cachedBlobUrl) {
            audio.src = cachedBlobUrl;
        }

        if (autoPlay && !isUser) {
            setIsLoadingAudio(true);
            audio.play()
                .then(() => {
                    setIsPlaying(true);
                    setIsLoadingAudio(false);
                })
                .catch(() => {
                    setIsPlaying(false);
                    setIsLoadingAudio(false);
                });
        }
    }, [cachedBlobUrl, autoPlay, isUser]);



    const togglePlay = async () => {

        if (isUser && !audioUrl && !cachedBlobUrl) {

            return;

        }



        let audio = audioRef.current;

        if (!audio) {

            audio = new Audio();

            audio.preload = "auto";

            audioRef.current = audio;

        }



        if (isPlaying) {

            audio.pause();

            setIsPlaying(false);

            return;

        }



        let targetBlobUrl = cachedBlobUrl;

        if (!targetBlobUrl) {

            setIsLoadingAudio(true);

            try {

                targetBlobUrl = await fetchAudioBlobUrl(audioUrl, spokenOpinion, isUser);

                setCachedBlobUrl(targetBlobUrl);

            } catch (err) {

                console.error("[VoiceNotePlayer] Fetch error:", err);

                setIsPlaying(false);

                setIsLoadingAudio(false);

                return;

            }

        }



        if (audio.src !== targetBlobUrl) {

            audio.src = targetBlobUrl;

        }



        try {

            setIsLoadingAudio(true);

            await audio.play();

            setIsPlaying(true);

            setIsLoadingAudio(false);

        } catch (err) {

            console.error("[VoiceNotePlayer] Play error:", err);

            setIsPlaying(false);

            setIsLoadingAudio(false);

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



