import { useCallback, useEffect, useRef, useState } from "react";
import { usePlayer } from "../../contexts/PlayerContext";
import { api, coverUrl, fmtTime } from "../../lib/api";
import { JogWheel } from "./JogWheel";
import { MixerChannel } from "./MixerChannel";
import { Crossfader } from "./Crossfader";
import { PerformancePads } from "./PerformancePads";
import { FullWaveform, ZoomedWaveform } from "./DualWaveform";
import { Play, Pause, SkipBack, SkipForward, Volume2, VolumeX } from "lucide-react";

export const DjConsole = ({ mix, onPlayToggle, onSeek, isCurrent }) => {
    const player = usePlayer();
    const time = isCurrent ? player.currentTime : 0;
    const dur = isCurrent && player.duration ? player.duration : mix.duration || 0;
    const tracks = mix.tracks || [];
    const trackIndex = isCurrent ? player.currentTrackIndex : -1;
    const playing = isCurrent && player.playing;

    // Fetch real peaks once - falls back to synthetic if not ready
    const [peaks, setPeaks] = useState(null);
    useEffect(() => {
        let alive = true;
        api.waveform(mix.id).then((data) => {
            if (alive && data?.ready && data.peaks?.length) {
                setPeaks(data.peaks);
            }
        }).catch(() => {});
        return () => { alive = false; };
    }, [mix.id]);

    // Alternating decks from context (when this mix is the active one)
    const decksFromCtx = isCurrent ? player.decks : null;
    const fallbackDeck = {
        active: "A",
        deckA: { track: tracks[0] || null, artwork: coverUrl(mix), isActive: true, isPreview: false },
        deckB: { track: tracks[1] || null, artwork: null, isActive: false, isPreview: true },
    };
    const decks = decksFromCtx || fallbackDeck;
    const activeSide = decks.active;
    const activeTrack = activeSide === "A" ? decks.deckA.track : decks.deckB.track;
    const previewTrack = activeSide === "A" ? decks.deckB.track : decks.deckA.track;
    const masterBpm = activeTrack?.bpm || mix.bpm;
    const masterKey = activeTrack?.camelot || mix.camelot;

    const remaining = previewTrack ? Math.max(0, previewTrack.start_seconds - time) : Math.max(0, dur - time);

    // Drag scrub support: throttle seeks during drag, commit on release
    const scrubAccumRef = useRef(0);
    const onJogScrub = useCallback((deltaSeconds) => {
        // accumulate; we'll apply via onScrubEnd to avoid thrashing the audio element
        scrubAccumRef.current += deltaSeconds;
        // For live feedback, do a soft seek every accumulator frame
        if (Math.abs(scrubAccumRef.current) > 0.25) {
            const target = (player.currentTime || 0) + scrubAccumRef.current;
            player.seek(Math.max(0, target));
            scrubAccumRef.current = 0;
        }
    }, [player]);

    const onJogScrubEnd = useCallback(() => {
        if (Math.abs(scrubAccumRef.current) > 0.05) {
            player.seek(Math.max(0, (player.currentTime || 0) + scrubAccumRef.current));
        }
        scrubAccumRef.current = 0;
    }, [player]);

    return (
        <div data-testid="dj-console" className="border border-[#1A1D2E] bg-gradient-to-b from-[#0a0c14] to-[#050608] relative overflow-hidden scanlines">
            {/* Top bar */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-[#1A1D2E] bg-black/40">
                <div className="flex items-center gap-3">
                    <span className="w-2 h-2 rounded-full bg-neon-red animate-pulse" />
                    <span className="label text-neon-red">REC</span>
                    <span className="label text-zinc-500">MIXDECK · XD-01</span>
                    <span className="label text-zinc-600 hidden md:inline">// LIVE ON {activeSide === "A" ? "DECK A" : "DECK B"}</span>
                </div>
                <div className="flex items-center gap-2">
                    <span className="label text-neon-cyan">MASTER</span>
                    <span className="font-display font-black text-neon-cyan text-sm">{masterBpm || "—"}</span>
                    <span className="label text-zinc-500">BPM</span>
                    <div className="w-px h-4 bg-[#1A1D2E] mx-2" />
                    {masterKey && (
                        <span className="label px-1.5 py-0.5 border border-neon-cyan/40 text-neon-cyan">{masterKey}</span>
                    )}
                </div>
            </div>

            {/* Display screen */}
            <div className="px-4 pt-3 pb-2 bg-black/60 border-b border-[#1A1D2E]">
                {/* Active deck info */}
                <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2 min-w-0">
                        <span
                            className="label transition-colors"
                            style={{ color: activeSide === "A" ? "#00F0FF" : "#39FF14", fontSize: 10 }}
                        >
                            DECK {activeSide} · LIVE
                        </span>
                        <span className="font-ui text-sm text-white truncate">
                            {activeTrack?.title || mix.title}
                        </span>
                        {activeTrack?.artist && (
                            <span className="label text-zinc-500 truncate hidden md:inline">· {activeTrack.artist}</span>
                        )}
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                        {activeTrack?.bpm && (
                            <span className="font-display font-bold text-neon-green" style={{ fontSize: 13 }}>{activeTrack.bpm}</span>
                        )}
                        <span className="font-mono text-neon-green glow-green" style={{ fontSize: 13 }}>{fmtTime(time)}</span>
                        <span className="font-mono text-zinc-500" style={{ fontSize: 13 }}>-{fmtTime(remaining)}</span>
                    </div>
                </div>
                <ZoomedWaveform mixId={mix.id} currentTime={time} duration={dur} tracks={tracks} onSeek={onSeek} height={80} peaks={peaks} />
                <div className="mt-1">
                    <FullWaveform mixId={mix.id} currentTime={time} duration={dur} tracks={tracks} onSeek={onSeek} height={36} peaks={peaks} />
                </div>
                {/* Preview deck info */}
                <div className="flex items-center justify-between mt-1">
                    <div className="flex items-center gap-2 min-w-0">
                        <span
                            className="label transition-colors"
                            style={{ color: activeSide === "A" ? "#39FF14" : "#00F0FF", fontSize: 10 }}
                        >
                            DECK {activeSide === "A" ? "B" : "A"} · NEXT
                        </span>
                        <span className="font-ui text-sm text-zinc-400 truncate">
                            {previewTrack ? previewTrack.title : "—"}
                        </span>
                        {previewTrack?.artist && (
                            <span className="label text-zinc-600 truncate hidden md:inline">· {previewTrack.artist}</span>
                        )}
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                        {previewTrack?.bpm && (
                            <span className="font-display font-bold text-zinc-400" style={{ fontSize: 12 }}>{previewTrack.bpm}</span>
                        )}
                        {previewTrack?.camelot && (
                            <span className="label px-1 border border-neon-cyan/30 text-neon-cyan" style={{ fontSize: 10 }}>{previewTrack.camelot}</span>
                        )}
                    </div>
                </div>
            </div>

            {/* Decks + mixer */}
            <div className="grid grid-cols-1 md:grid-cols-[auto_1fr_auto] gap-4 p-4 md:p-6 items-center">
                <div className="flex flex-col items-center gap-3">
                    <JogWheel
                        mix={mix}
                        track={decks.deckA.track}
                        art={decks.deckA.artwork}
                        playing={playing && decks.deckA.isActive}
                        currentTime={decks.deckA.isActive ? time : 0}
                        duration={decks.deckA.isActive ? dur : (decks.deckA.track ? 1 : 0)}
                        bpm={decks.deckA.track?.bpm || (decks.deckA.isActive ? mix.bpm : null)}
                        label="A"
                        side="left"
                        active={decks.deckA.isActive}
                        transitioning={isCurrent && player.transitioning}
                        size={240}
                        color="#00F0FF"
                        onScrub={decks.deckA.isActive ? onJogScrub : null}
                        onScrubEnd={decks.deckA.isActive ? onJogScrubEnd : null}
                    />
                    <div className="flex items-center gap-2 mt-3">
                        <TransportBtn onClick={() => player.seekRelative(-30)} icon={<SkipBack className="w-4 h-4" />} />
                        <button
                            onClick={onPlayToggle}
                            data-testid="deck-play-pause"
                            className={`w-14 h-14 rounded-full bg-neon-cyan text-black flex items-center justify-center shadow-[0_0_24px_rgba(0,240,255,0.6)] hover:scale-105 transition-transform ${
                                playing ? "" : "animate-pulse-glow"
                            }`}
                        >
                            {playing ? <Pause className="w-6 h-6 fill-current" /> : <Play className="w-6 h-6 fill-current ml-0.5" />}
                        </button>
                        <TransportBtn onClick={() => player.seekRelative(30)} icon={<SkipForward className="w-4 h-4" />} />
                    </div>
                </div>

                {/* Mixer */}
                <div className="flex flex-col gap-3 min-w-0">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                        <MixerChannel label="CH 1" color="#00F0FF" active={activeSide === "A"} />
                        <MixerChannel label="CH 2" color="#39FF14" active={activeSide === "B"} />
                        <MixerChannel label="CH 3" color="#FF9D00" active={false} />
                        <MixerChannel label="CH 4" color="#C800FF" active={false} />
                    </div>
                    <div className="flex items-center gap-3 px-3 py-2 border border-[#1A1D2E] bg-[#0a0c14]">
                        <button
                            onClick={() => player.setMuted(!player.muted)}
                            className="text-zinc-400 hover:text-neon-cyan transition-colors"
                            aria-label="mute"
                        >
                            {player.muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
                        </button>
                        <input
                            type="range"
                            min={0}
                            max={1}
                            step={0.01}
                            value={player.volume}
                            onChange={(e) => player.setVolume(parseFloat(e.target.value))}
                            className="flex-1"
                            style={{ "--seek": `${player.volume * 100}%` }}
                            aria-label="master volume"
                        />
                        <span className="label" style={{ fontSize: 9 }}>MASTER</span>
                    </div>
                    <Crossfader activeSide={activeSide} />
                </div>

                <div className="flex flex-col items-center gap-3">
                    <JogWheel
                        mix={mix}
                        track={decks.deckB.track}
                        art={decks.deckB.artwork}
                        playing={playing && decks.deckB.isActive}
                        currentTime={decks.deckB.isActive ? time : 0}
                        duration={decks.deckB.isActive ? dur : (decks.deckB.track ? 1 : 0)}
                        bpm={decks.deckB.track?.bpm || (decks.deckB.isActive ? mix.bpm : null)}
                        label="B"
                        side="right"
                        active={decks.deckB.isActive}
                        transitioning={isCurrent && player.transitioning}
                        size={240}
                        color="#39FF14"
                        onScrub={decks.deckB.isActive ? onJogScrub : null}
                        onScrubEnd={decks.deckB.isActive ? onJogScrubEnd : null}
                    />
                    <div className="text-center" style={{ minHeight: 56 }}>
                        <div className="label text-zinc-500">NEXT CUE POINT</div>
                        <div className="font-mono text-neon-green text-sm mt-1">
                            {previewTrack ? fmtTime(previewTrack.start_seconds) : "END OF MIX"}
                        </div>
                        <div className="label text-zinc-600 truncate max-w-[200px]">
                            {previewTrack?.title || ""}
                        </div>
                    </div>
                </div>
            </div>

            <div className="px-4 md:px-6 pb-5 pt-1">
                <div className="flex items-center justify-between mb-2">
                    <span className="label text-neon-cyan">HOT CUES · PERFORMANCE PADS</span>
                    <span className="label text-zinc-600">TAP TO JUMP</span>
                </div>
                <PerformancePads tracks={tracks} currentIndex={trackIndex} onJump={onSeek} />
            </div>
        </div>
    );
};

const TransportBtn = ({ onClick, icon }) => (
    <button
        onClick={onClick}
        className="w-12 h-12 border border-[#1A1D2E] hover:border-neon-cyan hover:text-neon-cyan text-zinc-300 flex items-center justify-center transition-colors"
    >
        {icon}
    </button>
);
