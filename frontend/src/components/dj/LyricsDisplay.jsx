import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../lib/api";
import { Type, EyeOff, Sliders, Loader2 } from "lucide-react";

/**
 * Synced-lyrics HUD overlay. Subscribes to the player's current track and
 * displays the active lyric line in a minimal, broadcast-style centered band.
 *
 * Layout:
 *   - Previous line (faint, above)
 *   - Current line (centered, glowing, bouncing dot)
 *   - Next line (faint, below)
 *
 * Lyrics are fetched from LRCLIB via /api/tracks/lyrics, cached per track in
 * the backend. Per-track offset slider lets the user nudge ±5s when DJ
 * pitch-bending makes lyrics drift.
 *
 * Track timing: LRC timestamps are relative to the START of the original
 * track (0:00 = first beat of the song). In a continuous DJ mix the track
 * actually starts at `track.start_seconds` in the mix's timeline. So the
 * lyric we want to display when the mix is at `mixTime` seconds is the one
 * whose LRC time is <= (mixTime - track.start_seconds + offset).
 *
 * Props:
 *   track: the currently playing track from the cue sheet ({title, artist,
 *          start_seconds, ...}) or null
 *   currentTime: current playback position in the mix (seconds)
 *   bpm: current BPM (drives the subtle pulse animation)
 */
const OFFSET_STORE_KEY = "mixdeck_lyric_offsets";

const getStoredOffset = (artist, title) => {
    try {
        const raw = localStorage.getItem(OFFSET_STORE_KEY);
        if (!raw) return 0;
        const map = JSON.parse(raw);
        return map[`${artist}|${title}`] || 0;
    } catch {
        return 0;
    }
};

const setStoredOffset = (artist, title, value) => {
    try {
        const raw = localStorage.getItem(OFFSET_STORE_KEY);
        const map = raw ? JSON.parse(raw) : {};
        map[`${artist}|${title}`] = value;
        localStorage.setItem(OFFSET_STORE_KEY, JSON.stringify(map));
    } catch {
        /* ignore */
    }
};

const STORE_KEY_HIDDEN = "mixdeck_lyrics_hidden";

export const LyricsDisplay = ({ track, currentTime, bpm }) => {
    const [lyrics, setLyrics] = useState(null); // {synced, plain, source, found}
    const [loading, setLoading] = useState(false);
    const [offset, setOffset] = useState(0);
    const [showOffset, setShowOffset] = useState(false);
    const [hidden, setHidden] = useState(() => {
        try { return localStorage.getItem(STORE_KEY_HIDDEN) === "1"; } catch { return false; }
    });
    const reqIdRef = useRef(0);

    const artist = track?.artist || "";
    const title = track?.title || "";
    const trackStart = track?.start_seconds || 0;

    // Fetch lyrics when the current track changes
    useEffect(() => {
        if (!artist && !title) {
            setLyrics(null);
            return;
        }
        setLoading(true);
        const reqId = ++reqIdRef.current;
        api.trackLyrics(artist, title)
            .then((data) => {
                if (reqId !== reqIdRef.current) return; // stale response
                setLyrics(data);
                setOffset(getStoredOffset(artist, title));
            })
            .catch(() => {
                if (reqId !== reqIdRef.current) return;
                setLyrics({ synced: [], plain: "", source: null, found: false });
            })
            .finally(() => {
                if (reqId === reqIdRef.current) setLoading(false);
            });
    }, [artist, title]);

    const synced = lyrics?.synced || [];
    const trackTime = Math.max(0, (currentTime || 0) - trackStart + offset);

    // Find current/prev/next lyric lines based on trackTime
    const { current, prev, next, currentIdx } = useMemo(() => {
        if (!synced.length) return { current: null, prev: null, next: null, currentIdx: -1 };
        // Binary search for the line whose time <= trackTime
        let lo = 0, hi = synced.length - 1, idx = -1;
        while (lo <= hi) {
            const mid = (lo + hi) >> 1;
            if (synced[mid].time <= trackTime) {
                idx = mid;
                lo = mid + 1;
            } else {
                hi = mid - 1;
            }
        }
        return {
            currentIdx: idx,
            prev: idx > 0 ? synced[idx - 1] : null,
            current: idx >= 0 ? synced[idx] : null,
            next: idx < synced.length - 1 ? synced[idx + 1] : null,
        };
    }, [synced, trackTime]);

    if (hidden) {
        // Tiny restore handle
        return (
            <button
                onClick={() => {
                    setHidden(false);
                    try { localStorage.setItem(STORE_KEY_HIDDEN, "0"); } catch { /* noop */ }
                }}
                data-testid="lyrics-show"
                className="label flex items-center gap-1.5 px-2 py-1 border border-[#1A1D2E] text-zinc-500 hover:text-neon-cyan hover:border-neon-cyan/40 transition-colors mt-2"
                title="Show lyrics"
            >
                <Type className="w-3 h-3" /> SHOW LYRICS
            </button>
        );
    }

    // Bouncing dot - drives off BPM so it feels musical (default 120 -> 2Hz)
    const pulseDur = bpm ? Math.max(0.3, 60 / bpm) : 0.5;

    const renderState = () => {
        if (loading && !synced.length) {
            return (
                <span className="text-zinc-600 font-mono text-xs flex items-center gap-2">
                    <Loader2 className="w-3 h-3 animate-spin" /> FETCHING LYRICS…
                </span>
            );
        }
        if (!lyrics?.found) {
            return (
                <span className="text-zinc-700 font-mono text-xs italic" data-testid="lyrics-empty">
                    {artist || title ? "♪ no lyrics available" : "♪ instrumental"}
                </span>
            );
        }
        if (lyrics.found && !synced.length) {
            return (
                <span className="text-zinc-600 font-mono text-xs italic" data-testid="lyrics-unsynced">
                    ♪ plain lyrics available (not synced)
                </span>
            );
        }
        if (!current) {
            // Before first line - countdown / intro state
            const firstAt = synced[0]?.time || 0;
            const wait = Math.max(0, firstAt - trackTime);
            return (
                <span className="text-zinc-600 font-mono text-xs" data-testid="lyrics-intro">
                    ♪ vocals in {wait < 60 ? `${Math.ceil(wait)}s` : "—"}
                </span>
            );
        }
        return current.text;
    };

    return (
        <div
            data-testid="lyrics-display"
            className="relative border-t border-b border-[#1A1D2E] bg-[#070912] py-3 px-4 mt-1 overflow-hidden scanlines"
        >
            {/* HUD label */}
            <div className="absolute top-1 left-3 flex items-center gap-1.5 pointer-events-none">
                <Type className="w-2.5 h-2.5 text-neon-cyan/60" />
                <span className="label text-neon-cyan/60" style={{ fontSize: 8 }}>// LYRICS</span>
                {lyrics?.source && (
                    <span className="label text-zinc-700" style={{ fontSize: 8 }}>· {lyrics.source}</span>
                )}
            </div>

            {/* Top-right controls */}
            <div className="absolute top-1 right-2 flex items-center gap-1 pointer-events-auto">
                {synced.length > 0 && (
                    <button
                        onClick={() => setShowOffset((v) => !v)}
                        data-testid="lyrics-offset-toggle"
                        title="Adjust sync offset"
                        className={`p-1 transition-colors ${showOffset ? "text-neon-cyan" : "text-zinc-600 hover:text-neon-cyan"}`}
                    >
                        <Sliders className="w-2.5 h-2.5" />
                    </button>
                )}
                <button
                    onClick={() => {
                        setHidden(true);
                        try { localStorage.setItem(STORE_KEY_HIDDEN, "1"); } catch { /* noop */ }
                    }}
                    data-testid="lyrics-hide"
                    title="Hide lyrics"
                    className="p-1 text-zinc-600 hover:text-neon-red transition-colors"
                >
                    <EyeOff className="w-2.5 h-2.5" />
                </button>
            </div>

            {/* Offset slider (hidden by default) */}
            {showOffset && synced.length > 0 && (
                <div
                    data-testid="lyrics-offset-panel"
                    className="absolute top-7 right-2 bg-black/90 border border-[#1A1D2E] px-2 py-1.5 flex items-center gap-2 z-10"
                >
                    <span className="label text-zinc-500" style={{ fontSize: 9 }}>OFFSET</span>
                    <input
                        type="range"
                        min={-5}
                        max={5}
                        step={0.1}
                        value={offset}
                        onChange={(e) => {
                            const v = parseFloat(e.target.value);
                            setOffset(v);
                            setStoredOffset(artist, title, v);
                        }}
                        className="w-28 accent-neon-cyan"
                        data-testid="lyrics-offset-slider"
                    />
                    <span className="font-mono text-neon-cyan tabular-nums" style={{ fontSize: 10, minWidth: 32, textAlign: "right" }}>
                        {offset > 0 ? "+" : ""}{offset.toFixed(1)}s
                    </span>
                </div>
            )}

            {/* Three-line stack: prev / current / next */}
            <div className="flex flex-col items-center justify-center gap-0.5 min-h-[80px] mt-1 text-center">
                <div
                    data-testid="lyric-prev"
                    className="font-ui text-xs text-zinc-700 truncate max-w-full transition-opacity duration-500"
                    style={{ opacity: prev ? 0.6 : 0 }}
                >
                    {prev?.text || "·"}
                </div>
                <div
                    data-testid="lyric-current"
                    key={currentIdx}
                    className="font-display font-bold text-sm md:text-base text-neon-cyan glow-cyan tracking-wide flex items-center gap-2 max-w-full lyric-fade-in"
                    style={{
                        textShadow: "0 0 12px rgba(0,240,255,0.4), 0 0 24px rgba(0,240,255,0.15)",
                    }}
                >
                    {current && synced.length > 0 && (
                        <span
                            className="inline-block w-1.5 h-1.5 rounded-full bg-neon-cyan shrink-0"
                            style={{
                                animation: `lyricPulse ${pulseDur}s ease-in-out infinite`,
                                boxShadow: "0 0 8px rgba(0,240,255,0.9)",
                            }}
                            aria-hidden
                        />
                    )}
                    <span className="truncate">{renderState()}</span>
                </div>
                <div
                    data-testid="lyric-next"
                    className="font-ui text-xs text-zinc-700 truncate max-w-full transition-opacity duration-500"
                    style={{ opacity: next ? 0.6 : 0 }}
                >
                    {next?.text || "·"}
                </div>
            </div>

            <style>{`
                @keyframes lyricPulse {
                    0%, 100% { transform: scale(1); opacity: 0.7; }
                    50% { transform: scale(1.6); opacity: 1; }
                }
                .lyric-fade-in {
                    animation: lyricFadeIn 0.55s ease-out;
                }
                @keyframes lyricFadeIn {
                    from { opacity: 0; transform: translateY(4px); }
                    to { opacity: 1; transform: translateY(0); }
                }
            `}</style>
        </div>
    );
};
