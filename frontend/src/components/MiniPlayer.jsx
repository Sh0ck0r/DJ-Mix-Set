import { Link } from "react-router-dom";
import { Play, Pause, SkipForward, SkipBack, Volume2, VolumeX, Maximize2 } from "lucide-react";
import { usePlayer } from "../contexts/PlayerContext";
import { coverUrl, fmtTime } from "../lib/api";
import { VuMeter } from "./VuMeter";

export const MiniPlayer = () => {
    const { mix, playing, currentTime, duration, toggle, seek, seekRelative, volume, muted, setVolume, setMuted, currentTrackIndex, trackArtwork } = usePlayer();
    if (!mix) return null;
    const cover = coverUrl(mix);
    const displayCover = trackArtwork || cover;
    const progress = duration ? (currentTime / duration) * 100 : 0;
    const currentTrack = mix.tracks?.[currentTrackIndex];

    return (
        <div
            data-testid="mini-player"
            className="fixed bottom-0 left-0 right-0 z-50 backdrop-blur-xl bg-[#050505]/85 border-t border-neon-cyan/30"
        >
            <div
                className="absolute -top-[1px] left-0 h-[2px] bg-neon-cyan shadow-[0_0_10px_#00F0FF]"
                style={{ width: `${progress}%` }}
            />
            <div className="max-w-[1600px] mx-auto px-3 sm:px-6 h-20 sm:h-24 grid grid-cols-[auto_1fr_auto] gap-3 sm:gap-6 items-center">
                {/* left: cover + title */}
                <Link to={`/mix/${mix.id}`} className="flex items-center gap-3 min-w-0 group">
                    <div className="relative w-14 h-14 sm:w-16 sm:h-16 bg-black border border-[#1A1D2E] overflow-hidden shrink-0">
                        {cover ? (
                            <img src={cover} alt={mix.title} className="absolute inset-0 w-full h-full object-cover" />
                        ) : (
                            <div className="absolute inset-0 grid-bg" />
                        )}
                        {trackArtwork ? (
                            <img
                                key={trackArtwork}
                                src={trackArtwork}
                                alt="track art"
                                className="absolute inset-0 w-full h-full object-cover"
                                style={{ animation: "fadeIn 0.6s ease-in-out forwards", opacity: 0 }}
                            />
                        ) : null}
                        {playing && (
                            <div className="absolute inset-0 flex items-end justify-center gap-0.5 p-1.5 bg-black/30">
                                {[0, 1, 2, 3].map((i) => (
                                    <span
                                        key={i}
                                        className="w-0.5 bg-neon-cyan animate-pulse"
                                        style={{ height: `${30 + (i % 2) * 30}%`, animationDelay: `${i * 120}ms` }}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                    <div className="min-w-0 hidden sm:block">
                        <div className="font-display font-bold text-sm text-white truncate group-hover:text-neon-cyan transition-colors">
                            {currentTrack?.title || mix.title}
                        </div>
                        <div className="label truncate">
                            {currentTrack ? `${currentTrack.artist || mix.artist}` : mix.artist}
                        </div>
                    </div>
                </Link>

                {/* center: controls */}
                <div className="flex flex-col items-center gap-1.5 min-w-0">
                    <div className="flex items-center gap-2 sm:gap-4">
                        <button
                            onClick={() => seekRelative(-15)}
                            data-testid="mini-prev-button"
                            className="text-zinc-400 hover:text-neon-cyan transition-colors"
                            aria-label="Back 15s"
                        >
                            <SkipBack className="w-5 h-5" />
                        </button>
                        <button
                            onClick={toggle}
                            data-testid="mini-play-pause"
                            className={`w-10 h-10 sm:w-11 sm:h-11 rounded-full bg-neon-cyan text-black flex items-center justify-center shadow-[0_0_20px_rgba(0,240,255,0.6)] hover:scale-105 transition-transform ${
                                playing ? "" : "animate-pulse-glow"
                            }`}
                            aria-label={playing ? "Pause" : "Play"}
                        >
                            {playing ? <Pause className="w-5 h-5 fill-current" /> : <Play className="w-5 h-5 fill-current ml-0.5" />}
                        </button>
                        <button
                            onClick={() => seekRelative(15)}
                            data-testid="mini-next-button"
                            className="text-zinc-400 hover:text-neon-cyan transition-colors"
                            aria-label="Forward 15s"
                        >
                            <SkipForward className="w-5 h-5" />
                        </button>
                    </div>
                    <div className="hidden sm:flex items-center gap-2 w-full max-w-md">
                        <span className="font-mono text-[10px] text-neon-green w-10 text-right">{fmtTime(currentTime)}</span>
                        <input
                            data-testid="mini-seek"
                            type="range"
                            min={0}
                            max={duration || 0}
                            step={0.1}
                            value={currentTime || 0}
                            onChange={(e) => seek(parseFloat(e.target.value))}
                            className="flex-1"
                            style={{ "--seek": `${progress}%` }}
                        />
                        <span className="font-mono text-[10px] text-zinc-500 w-10">{fmtTime(duration)}</span>
                    </div>
                </div>

                {/* right: volume + expand */}
                <div className="flex items-center gap-2 sm:gap-4">
                    <div className="hidden md:flex items-center gap-1 h-10">
                        <VuMeter orientation="vertical" label="left" />
                        <VuMeter orientation="vertical" label="right" />
                    </div>
                    <button
                        onClick={() => setMuted(!muted)}
                        data-testid="mute-button"
                        className="text-zinc-400 hover:text-neon-cyan transition-colors hidden sm:block"
                        aria-label={muted ? "Unmute" : "Mute"}
                    >
                        {muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
                    </button>
                    <input
                        data-testid="volume-slider"
                        type="range"
                        min={0}
                        max={1}
                        step={0.01}
                        value={volume}
                        onChange={(e) => setVolume(parseFloat(e.target.value))}
                        className="hidden sm:block w-20"
                        style={{ "--seek": `${volume * 100}%` }}
                    />
                    <Link
                        to={`/mix/${mix.id}`}
                        data-testid="expand-player"
                        className="text-zinc-400 hover:text-neon-cyan transition-colors"
                        aria-label="Open full player"
                    >
                        <Maximize2 className="w-4 h-4" />
                    </Link>
                </div>
            </div>
        </div>
    );
};
