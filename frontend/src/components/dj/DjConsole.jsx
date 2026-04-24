import { usePlayer } from "../../contexts/PlayerContext";
import { coverUrl, fmtTime } from "../../lib/api";
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
    const currentTrack = tracks[trackIndex] || null;
    const nextTrack = tracks[trackIndex + 1] || null;
    const playing = isCurrent && player.playing;
    const liveArt = isCurrent ? player.trackArtwork : null;
    const coverA = liveArt || coverUrl(mix);

    const remaining = nextTrack ? nextTrack.start_seconds - time : dur - time;

    return (
        <div
            data-testid="dj-console"
            className="border border-[#1A1D2E] bg-gradient-to-b from-[#0a0c14] to-[#050608] relative overflow-hidden scanlines"
        >
            {/* Top bar - device name + LEDs */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-[#1A1D2E] bg-black/40">
                <div className="flex items-center gap-3">
                    <span className="w-2 h-2 rounded-full bg-neon-red animate-pulse" />
                    <span className="label text-neon-red">REC</span>
                    <span className="label text-zinc-500">MIXDECK · XD-01</span>
                </div>
                <div className="flex items-center gap-2">
                    <span className="label text-neon-cyan">MASTER</span>
                    <span className="font-display font-black text-neon-cyan text-sm">
                        {mix.bpm || (currentTrack?.bpm) || "—"}
                    </span>
                    <span className="label text-zinc-500">BPM</span>
                    <div className="w-px h-4 bg-[#1A1D2E] mx-2" />
                    {(currentTrack?.camelot || mix.camelot) && (
                        <span className="label px-1.5 py-0.5 border border-neon-cyan/40 text-neon-cyan">
                            {currentTrack?.camelot || mix.camelot}
                        </span>
                    )}
                </div>
            </div>

            {/* Display screen: dual waveforms + track info */}
            <div className="px-4 pt-3 pb-2 bg-black/60 border-b border-[#1A1D2E]">
                {/* Deck A info row */}
                <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2 min-w-0">
                        <span className="label text-neon-cyan" style={{ fontSize: 10 }}>DECK A</span>
                        <span className="font-ui text-sm text-white truncate">
                            {currentTrack?.title || mix.title}
                        </span>
                        {currentTrack?.artist && (
                            <span className="label text-zinc-500 truncate hidden md:inline">· {currentTrack.artist}</span>
                        )}
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                        {currentTrack?.bpm && (
                            <span className="font-display font-bold text-neon-green" style={{ fontSize: 13 }}>
                                {currentTrack.bpm}
                            </span>
                        )}
                        <span className="font-mono text-neon-green glow-green" style={{ fontSize: 13 }}>
                            {fmtTime(time)}
                        </span>
                        <span className="font-mono text-zinc-500" style={{ fontSize: 13 }}>
                            -{fmtTime(remaining)}
                        </span>
                    </div>
                </div>
                {/* Zoomed waveform - CDJ style */}
                <ZoomedWaveform
                    mixId={mix.id}
                    currentTime={time}
                    duration={dur}
                    tracks={tracks}
                    onSeek={onSeek}
                    height={80}
                />
                {/* Full-mix overview */}
                <div className="mt-1">
                    <FullWaveform
                        mixId={mix.id}
                        currentTime={time}
                        duration={dur}
                        tracks={tracks}
                        onSeek={onSeek}
                        height={36}
                    />
                </div>
                {/* Deck B / next track preview */}
                <div className="flex items-center justify-between mt-1">
                    <div className="flex items-center gap-2 min-w-0">
                        <span className="label text-neon-green" style={{ fontSize: 10 }}>DECK B · NEXT</span>
                        <span className="font-ui text-sm text-zinc-400 truncate">
                            {nextTrack ? nextTrack.title : "—"}
                        </span>
                        {nextTrack?.artist && (
                            <span className="label text-zinc-600 truncate hidden md:inline">· {nextTrack.artist}</span>
                        )}
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                        {nextTrack?.bpm && (
                            <span className="font-display font-bold text-zinc-400" style={{ fontSize: 12 }}>
                                {nextTrack.bpm}
                            </span>
                        )}
                        {nextTrack?.camelot && (
                            <span className="label px-1 border border-neon-cyan/30 text-neon-cyan" style={{ fontSize: 10 }}>
                                {nextTrack.camelot}
                            </span>
                        )}
                    </div>
                </div>
            </div>

            {/* Main deck row - jogs + mixer */}
            <div className="grid grid-cols-1 md:grid-cols-[auto_1fr_auto] gap-4 p-4 md:p-6 items-center">
                {/* Left jog - deck A */}
                <div className="flex flex-col items-center gap-3">
                    <JogWheel
                        mix={mix}
                        art={coverA}
                        playing={playing}
                        currentTime={time}
                        duration={dur}
                        bpm={currentTrack?.bpm || mix.bpm}
                        label="A"
                        side="left"
                        active={true}
                        size={240}
                    />
                    {/* Transport row A */}
                    <div className="flex items-center gap-2">
                        <TransportBtn onClick={() => player.seekRelative(-30)} label="-30" />
                        <button
                            onClick={onPlayToggle}
                            data-testid="deck-play-pause"
                            className={`w-14 h-14 rounded-full bg-neon-cyan text-black flex items-center justify-center shadow-[0_0_24px_rgba(0,240,255,0.6)] hover:scale-105 transition-transform ${
                                playing ? "" : "animate-pulse-glow"
                            }`}
                        >
                            {playing ? <Pause className="w-6 h-6 fill-current" /> : <Play className="w-6 h-6 fill-current ml-0.5" />}
                        </button>
                        <TransportBtn onClick={() => player.seekRelative(30)} label="+30" />
                    </div>
                </div>

                {/* Center mixer */}
                <div className="flex flex-col gap-3 min-w-0">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                        <MixerChannel label="CH 1" color="#00F0FF" active={true} />
                        <MixerChannel label="CH 2" color="#39FF14" active={false} />
                        <MixerChannel label="CH 3" color="#FF9D00" active={false} />
                        <MixerChannel label="CH 4" color="#C800FF" active={false} />
                    </div>
                    {/* Volume master + crossfader */}
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
                    <Crossfader />
                </div>

                {/* Right jog - deck B (preview next track) */}
                <div className="flex flex-col items-center gap-3">
                    <JogWheel
                        mix={mix}
                        art={null}
                        playing={false}
                        currentTime={0}
                        duration={nextTrack ? 60 : 0}
                        bpm={nextTrack?.bpm}
                        label="B"
                        side="right"
                        active={false}
                        size={240}
                    />
                    <div className="text-center" style={{ minHeight: 56 }}>
                        <div className="label text-zinc-500">NEXT CUE POINT</div>
                        <div className="font-mono text-neon-green text-sm mt-1">
                            {nextTrack ? fmtTime(nextTrack.start_seconds) : "END OF MIX"}
                        </div>
                        <div className="label text-zinc-600 truncate max-w-[200px]">
                            {nextTrack?.title || ""}
                        </div>
                    </div>
                </div>
            </div>

            {/* Performance pads */}
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

const TransportBtn = ({ onClick, label, testid }) => (
    <button
        onClick={onClick}
        data-testid={testid}
        className="w-12 h-12 border border-[#1A1D2E] hover:border-neon-cyan hover:text-neon-cyan text-zinc-300 flex items-center justify-center transition-colors font-mono text-xs"
    >
        {label.startsWith("-") ? <SkipBack className="w-4 h-4" /> : label.startsWith("+") ? <SkipForward className="w-4 h-4" /> : label}
    </button>
);
