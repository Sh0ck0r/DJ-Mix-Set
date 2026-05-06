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
    const [trackArtwork, setTrackArtwork] = useState(null);
    const [trackArtworkLoading, setTrackArtworkLoading] = useState(false);
    const [nextTrackArtwork, setNextTrackArtwork] = useState(null);
    const [transitioning, setTransitioning] = useState(false);
    const transitionTimeout = useRef(null);

    const audioRef = useRef(null);
    const sourceRef = useRef(null);

    // Lazily create audio element once
    useEffect(() => {
        const el = new Audio();
        el.crossOrigin = "anonymous";
        el.preload = "metadata";
        audioRef.current = el;
        // Expose for e2e tests + browser-console debugging. Harmless in prod.
        if (typeof window !== "undefined") window.__mixdeckAudio = el;

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

    // Auto-fetch track artwork from iTunes as tracks change (current + next)
    useEffect(() => {
        const tr = mix?.tracks?.[currentTrackIndex];
        const nextTr = mix?.tracks?.[currentTrackIndex + 1];

        // Briefly mark transitioning so jog wheels can crossfade
        setTransitioning(true);
        if (transitionTimeout.current) clearTimeout(transitionTimeout.current);
        transitionTimeout.current = setTimeout(() => setTransitioning(false), 1500);

        if (!tr || (!tr.title && !tr.artist)) {
            setTrackArtwork(null);
        } else {
            setTrackArtworkLoading(true);
            api.trackArtwork(tr.artist || mix.artist || "", tr.title || "")
                .then((res) => setTrackArtwork(res?.url || null))
                .catch(() => setTrackArtwork(null))
                .finally(() => setTrackArtworkLoading(false));
        }

        if (!nextTr || (!nextTr.title && !nextTr.artist)) {
            setNextTrackArtwork(null);
        } else {
            api.trackArtwork(nextTr.artist || mix.artist || "", nextTr.title || "")
                .then((res) => setNextTrackArtwork(res?.url || null))
                .catch(() => setNextTrackArtwork(null));
        }
    }, [mix?.id, currentTrackIndex]);

    // Alternating decks: even-indexed tracks (0,2,4) play on Deck A, odd on Deck B.
    // Inactive deck always previews the next track.
    const decks = useMemo(() => {
        const tracks = mix?.tracks || [];
        const idx = currentTrackIndex;
        if (idx < 0 || tracks.length === 0) {
            return {
                active: "A",
                deckA: { track: tracks[0] || null, artwork: trackArtwork, isActive: true, isPreview: false },
                deckB: { track: tracks[1] || null, artwork: nextTrackArtwork, isActive: false, isPreview: true },
            };
        }
        const active = idx % 2 === 0 ? "A" : "B";
        const activeTrack = tracks[idx] || null;
        const previewTrack = tracks[idx + 1] || null;
        if (active === "A") {
            return {
                active,
                deckA: { track: activeTrack, artwork: trackArtwork, isActive: true, isPreview: false },
                deckB: { track: previewTrack, artwork: nextTrackArtwork, isActive: false, isPreview: true },
            };
        }
        return {
            active,
            deckA: { track: previewTrack, artwork: nextTrackArtwork, isActive: false, isPreview: true },
            deckB: { track: activeTrack, artwork: trackArtwork, isActive: true, isPreview: false },
        };
    }, [mix, currentTrackIndex, trackArtwork, nextTrackArtwork]);

    // ===== MediaSession API: lock-screen / Bluetooth / CarPlay metadata + transport =====
    useEffect(() => {
        if (typeof navigator === "undefined" || !("mediaSession" in navigator) || !mix) return;
        const ms = navigator.mediaSession;
        const tr = mix.tracks?.[currentTrackIndex];
        const liveTitle = tr?.title || mix.title;
        const liveArtist = tr?.artist || mix.artist || "MIXDECK";
        const artworkSrc = trackArtwork || (mix.cover_filename || mix.cover_url || mix.source_cover_path
            ? (mix.cover_url || `${process.env.REACT_APP_BACKEND_URL || ""}/api/cover/${mix.id}`)
            : null);
        const artwork = artworkSrc ? [
            { src: artworkSrc, sizes: "512x512", type: "image/jpeg" },
            { src: artworkSrc, sizes: "256x256", type: "image/jpeg" },
        ] : [];
        try {
            ms.metadata = new window.MediaMetadata({
                title: liveTitle,
                artist: liveArtist,
                album: mix.title,
                artwork,
            });
        } catch {
            /* MediaMetadata not supported in this browser */
        }
        const safeSet = (action, handler) => {
            try { ms.setActionHandler(action, handler); } catch { /* unsupported */ }
        };
        safeSet("play", () => { audioRef.current?.play().catch(() => {}); });
        safeSet("pause", () => { audioRef.current?.pause(); });
        safeSet("seekbackward", (e) => {
            const skip = (e && e.seekOffset) || 15;
            seekRelative(-skip);
        });
        safeSet("seekforward", (e) => {
            const skip = (e && e.seekOffset) || 15;
            seekRelative(skip);
        });
        safeSet("seekto", (e) => {
            if (e && typeof e.seekTime === "number") seek(e.seekTime);
        });
        safeSet("previoustrack", () => {
            const tracks = mix.tracks || [];
            if (currentTrackIndex > 0) seek(tracks[currentTrackIndex - 1].start_seconds || 0);
            else seek(0);
        });
        safeSet("nexttrack", () => {
            const tracks = mix.tracks || [];
            if (currentTrackIndex >= 0 && currentTrackIndex < tracks.length - 1) {
                seek(tracks[currentTrackIndex + 1].start_seconds || 0);
            }
        });
        return () => {
            ["play", "pause", "seekbackward", "seekforward", "seekto", "previoustrack", "nexttrack"].forEach(
                (a) => { try { ms.setActionHandler(a, null); } catch { /* unsupported */ } }
            );
        };
    }, [mix, currentTrackIndex, trackArtwork, seek, seekRelative]);

    // ===== Update playbackState so OS shows correct play/pause =====
    useEffect(() => {
        if (typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
        navigator.mediaSession.playbackState = playing ? "playing" : "paused";
    }, [playing]);

    // ===== Update positionState so OS scrubber tracks correctly =====
    useEffect(() => {
        if (typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
        if (!duration || !Number.isFinite(duration)) return;
        try {
            navigator.mediaSession.setPositionState({
                duration,
                playbackRate: audioRef.current?.playbackRate || 1,
                position: Math.min(currentTime, duration),
            });
        } catch { /* setPositionState not supported in this browser */ }
    }, [currentTime, duration]);

    // ===== Resume position: save listener position per-mix to localStorage =====
    // Saved every 5 seconds + on pause/unmount. Cleared when mix completes.
    useEffect(() => {
        if (!mix?.id || !duration) return;
        const STORE_KEY = "mixdeck_resume";
        const SAVE_THRESHOLD = 15; // only save once we're > 15s into the mix
        const FORGET_TAIL = 30; // clear if listener is within last 30s (mix finished)
        const persist = () => {
            try {
                const raw = localStorage.getItem(STORE_KEY);
                const map = raw ? JSON.parse(raw) : {};
                const t = audioRef.current?.currentTime || 0;
                if (t < SAVE_THRESHOLD) return;
                if (duration && t > duration - FORGET_TAIL) {
                    delete map[mix.id];
                } else {
                    map[mix.id] = { t: Math.floor(t), at: Date.now(), title: mix.title };
                }
                localStorage.setItem(STORE_KEY, JSON.stringify(map));
            } catch { /* localStorage quota / parse errors are harmless */ }
        };
        const iv = setInterval(persist, 5000);
        const el = audioRef.current;
        el?.addEventListener("pause", persist);
        return () => {
            clearInterval(iv);
            persist();
            el?.removeEventListener("pause", persist);
        };
    }, [mix?.id, duration, mix?.title]);

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
        trackArtwork,
        nextTrackArtwork,
        trackArtworkLoading,
        decks,
        transitioning,
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
