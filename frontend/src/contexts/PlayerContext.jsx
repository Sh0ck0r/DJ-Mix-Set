import { createContext, useContext, useEffect, useMemo, useRef, useState, useCallback } from "react";
import { api, streamUrl } from "../lib/api";

const PlayerContext = createContext(null);

export const usePlayer = () => useContext(PlayerContext);

export const PlayerProvider = ({ children }) => {
    const [mix, setMix] = useState(null);
    const [playing, setPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [volume, setVolume] = useState(0.85);
    const [muted, setMuted] = useState(false);
    const [analyser, setAnalyser] = useState(null);
    const [audioCtx, setAudioCtx] = useState(null);

    const audioRef = useRef(null);
    const sourceRef = useRef(null);

    // Lazily create audio element once
    useEffect(() => {
        const el = new Audio();
        el.crossOrigin = "anonymous";
        el.preload = "metadata";
        audioRef.current = el;

        const onTime = () => setCurrentTime(el.currentTime || 0);
        const onDur = () => setDuration(el.duration || 0);
        const onPlay = () => setPlaying(true);
        const onPause = () => setPlaying(false);
        const onEnded = () => setPlaying(false);

        el.addEventListener("timeupdate", onTime);
        el.addEventListener("loadedmetadata", onDur);
        el.addEventListener("durationchange", onDur);
        el.addEventListener("play", onPlay);
        el.addEventListener("pause", onPause);
        el.addEventListener("ended", onEnded);

        return () => {
            el.pause();
            el.removeEventListener("timeupdate", onTime);
            el.removeEventListener("loadedmetadata", onDur);
            el.removeEventListener("durationchange", onDur);
            el.removeEventListener("play", onPlay);
            el.removeEventListener("pause", onPause);
            el.removeEventListener("ended", onEnded);
        };
    }, []);

    useEffect(() => {
        if (audioRef.current) {
            audioRef.current.volume = muted ? 0 : volume;
        }
    }, [volume, muted]);

    const ensureAnalyser = useCallback(() => {
        if (analyser || !audioRef.current) return analyser;
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const src = ctx.createMediaElementSource(audioRef.current);
            const an = ctx.createAnalyser();
            an.fftSize = 256;
            src.connect(an);
            an.connect(ctx.destination);
            sourceRef.current = src;
            setAudioCtx(ctx);
            setAnalyser(an);
            return an;
        } catch (e) {
            // happens if audio cross-origin blocks - it'll fall back gracefully
            console.warn("Analyser unavailable", e);
            return null;
        }
    }, [analyser]);

    const loadMix = useCallback(async (newMix, autoplay = true) => {
        const el = audioRef.current;
        if (!el || !newMix) return;
        const url = streamUrl(newMix);
        if (!url) return;
        if (mix?.id !== newMix.id) {
            el.src = url;
            el.load();
        }
        setMix(newMix);
        if (autoplay) {
            try {
                if (audioCtx?.state === "suspended") await audioCtx.resume();
                ensureAnalyser();
                await el.play();
                api.incPlay(newMix.id).catch(() => {});
            } catch (e) {
                console.warn("Play failed", e);
            }
        }
    }, [mix, audioCtx, ensureAnalyser]);

    const toggle = useCallback(async () => {
        const el = audioRef.current;
        if (!el || !mix) return;
        if (audioCtx?.state === "suspended") await audioCtx.resume();
        ensureAnalyser();
        if (el.paused) {
            try { await el.play(); } catch (e) { console.warn(e); }
        } else {
            el.pause();
        }
    }, [mix, audioCtx, ensureAnalyser]);

    const seek = useCallback((t) => {
        const el = audioRef.current;
        if (!el) return;
        el.currentTime = Math.max(0, Math.min(t, el.duration || t));
        setCurrentTime(el.currentTime);
    }, []);

    const seekRelative = useCallback((delta) => {
        const el = audioRef.current;
        if (!el) return;
        seek((el.currentTime || 0) + delta);
    }, [seek]);

    const stop = useCallback(() => {
        const el = audioRef.current;
        if (!el) return;
        el.pause();
        el.currentTime = 0;
    }, []);

    // Once metadata is loaded persist duration to backend if missing
    useEffect(() => {
        if (mix && duration && !mix.duration) {
            api.setDuration(mix.id, duration).catch(() => {});
        }
    }, [mix, duration]);

    const currentTrackIndex = useMemo(() => {
        if (!mix?.tracks?.length) return -1;
        const t = currentTime;
        let idx = -1;
        for (let i = 0; i < mix.tracks.length; i++) {
            if (mix.tracks[i].start_seconds <= t) idx = i;
            else break;
        }
        return idx;
    }, [mix, currentTime]);

    const value = {
        mix,
        playing,
        currentTime,
        duration,
        volume,
        muted,
        analyser,
        audioRef,
        currentTrackIndex,
        loadMix,
        toggle,
        seek,
        seekRelative,
        stop,
        setVolume,
        setMuted,
        ensureAnalyser,
    };

    return <PlayerContext.Provider value={value}>{children}</PlayerContext.Provider>;
};
