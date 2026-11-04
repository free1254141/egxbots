"use client";

import { useState, useEffect } from "react";

export interface ActiveVoicePlayback {
    id: string;
    role: "user" | "assistant" | "system";
    currentTime: number;
    duration: number;
    isPlaying: boolean;
    pause: () => void;
    stop: () => void;
}

let activeAudioInstance: {
    id: string;
    audio: HTMLAudioElement;
    stop: () => void;
} | null = null;

let currentPlaybackState: ActiveVoicePlayback | null = null;
const playbackListeners = new Set<(state: ActiveVoicePlayback | null) => void>();

export function useActiveVoicePlayback(): ActiveVoicePlayback | null {
    const [state, setState] = useState<ActiveVoicePlayback | null>(currentPlaybackState);

    useEffect(() => {
        playbackListeners.add(setState);
        return () => {
            playbackListeners.delete(setState);
        };
    }, []);

    return state;
}

export function formatVoiceTime(seconds: number): string {
    if (!seconds || isNaN(seconds) || !isFinite(seconds) || seconds < 0) return "0:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function registerGlobalPlayingAudio(
    id: string,
    audio: HTMLAudioElement,
    role: "user" | "assistant" | "system",
    onStop: () => void
) {
    // 1. If another voice note is already playing, stop it immediately!
    if (activeAudioInstance && activeAudioInstance.id !== id) {
        try {
            activeAudioInstance.audio.pause();
        } catch {}
        activeAudioInstance.stop();
    }

    const stopSelf = () => {
        try {
            audio.pause();
            audio.currentTime = 0;
        } catch {}
        onStop();
        if (activeAudioInstance?.id === id) {
            activeAudioInstance = null;
            currentPlaybackState = null;
            playbackListeners.forEach(listener => listener(null));
        }
    };

    activeAudioInstance = {
        id,
        audio,
        stop: stopSelf
    };

    currentPlaybackState = {
        id,
        role,
        currentTime: audio.currentTime || 0,
        duration: audio.duration || 0,
        isPlaying: true,
        pause: stopSelf,
        stop: stopSelf
    };
    playbackListeners.forEach(listener => listener(currentPlaybackState));
}

export function syncGlobalTime(id: string, currentTime: number, duration: number) {
    if (activeAudioInstance?.id === id && currentPlaybackState) {
        currentPlaybackState = {
            ...currentPlaybackState,
            currentTime,
            duration: duration > 0 ? duration : currentPlaybackState.duration
        };
        playbackListeners.forEach(listener => listener(currentPlaybackState));
    }
}

export function unregisterGlobalPlayingAudio(id: string) {
    if (activeAudioInstance?.id === id) {
        activeAudioInstance = null;
        currentPlaybackState = null;
        playbackListeners.forEach(listener => listener(null));
    }
}
