import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, coverUrl, fmtTime } from "../lib/api";
import { usePlayer } from "../contexts/PlayerContext";
import { Waveform } from "../components/Waveform";
import { VuMeter } from "../components/VuMeter";
import { CueTrackList } from "../components/CueTrackList";
import {
    Play, Pause, SkipBack, SkipForward, Volume2, VolumeX, ArrowLeft,
    Music, Clock, Activity, Headphones, Loader2,
} from "lucide-react";

export const MixDetail = () => {
    const { id } = useParams();
    const [mix, setMix] = useState(null);
    const [loading, setLoading] = useState(true);
    const player = usePlayer();
    const isCurrent = player.mix?.id === id;

    useEffect(() => {
        let alive = true;
        setLoading(true);
        api.getMix(id).then((m) => {
            if (alive) {
                setMix(m);
                setLoading(false);
            }
        }).catch(() => setLoading(false));
        return () => {
            alive = false;
        };
    }, [id]);

    if (loading) {
        return (
            <div className="py-20 flex items-center justify-center">
                <Loader2 className="w-8 h-8 text-neon-cyan animate-spin" />
            </div>
        );
    }
    if (!mix) {
        return (
            <div className="max-w-3xl mx-auto px-6 py-20 text-center">
                <p className="label mb-4">MIX NOT FOUND</p>
                <Link to="/" className="text-neon-cyan hover:underline">← Back to library</Link>
            </div>
        );
    }

    const cover = coverUrl(mix) || "https://images.unsplash.com/photo-1769120061986-a077f35b2569?w=800&q=80";
    const liveArt = isCurrent ? player.trackArtwork : null;
    const displayArt = liveArt || cover;
    const playable = !!(mix.audio_filename || mix.audio_url);
    const onPlayAll = () => {
        if (!playable) return;
        if (isCurrent) player.toggle();
        else player.loadMix(mix);
    };

    const time = isCurrent ? player.currentTime : 0;
    const dur = isCurrent && player.duration ? player.duration : mix.duration || 0;
    const trackIndex = isCurrent ? player.currentTrackIndex : -1;

    const onSeek = (t) => {
        if (!playable) return;
        if (!isCurrent) {
            player.loadMix(mix);
            // wait for metadata then seek
            const tryThis = () => {
                if (player.audioRef.current?.duration) {
                    player.seek(t);
                } else {
                    setTimeout(tryThis, 200);
                }
            };
            setTimeout(tryThis, 300);
        } else {
            player.seek(t);
        }
    };

    return (
        <div className="max-w-[1600px] mx-auto px-4 md:px-8 py-8 pb-32">
            <Link
                to="/"
                data-testid="back-to-library"
                className="label inline-flex items-center gap-2 hover:text-neon-cyan mb-6"
            >
                <ArrowLeft className="w-3 h-3" /> BACK TO LIBRARY
            </Link>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* LEFT: cover + meta */}
                <div className="lg:col-span-4 space-y-4">
                    <div className="relative aspect-square border border-[#1A1D2E] overflow-hidden bg-black scanlines">
                        <img
                            src={cover}
                            alt={mix.title}
                            className="absolute inset-0 w-full h-full object-cover"
                        />
                        {liveArt ? (
                            <img
                                key={liveArt}
                                src={liveArt}
                                alt="track art"
                                className="absolute inset-0 w-full h-full object-cover animate-[fade_0.6s_ease-in-out_forwards] opacity-0"
                                style={{ animation: "fadeIn 0.6s ease-in-out forwards" }}
                            />
                        ) : null}
                        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent pointer-events-none" />
                        {liveArt && (
                            <div className="absolute top-2 left-2 label bg-black/70 border border-neon-green/40 px-1.5 py-0.5 text-neon-green glow-green flex items-center gap-1" data-testid="now-playing-art-badge">
                                <span className="w-1.5 h-1.5 rounded-full bg-neon-green animate-pulse" />
                                NOW PLAYING ART
                            </div>
                        )}
                    </div>
                    <div className="space-y-3">
                        <div>
                            <span className="label">{mix.genre || "DJ MIX"}</span>
                            <h1 className="font-display font-black text-3xl sm:text-4xl uppercase leading-tight mt-1">
                                {mix.title}
                            </h1>
                            <p className="font-mono text-sm text-zinc-400 mt-2 flex items-center gap-2">
                                <Music className="w-4 h-4 text-neon-cyan" /> {mix.artist || "UNKNOWN ARTIST"}
                            </p>
                        </div>
                        {mix.description ? (
                            <p className="font-mono text-sm text-zinc-400 leading-relaxed border-l-2 border-neon-cyan/30 pl-3">
                                {mix.description}
                            </p>
                        ) : null}
                        <div className="grid grid-cols-3 gap-2 pt-2">
                            <Stat label="DURATION" value={fmtTime(dur)} icon={<Clock className="w-3 h-3" />} />
                            <Stat label="BPM" value={mix.bpm || "—"} icon={<Activity className="w-3 h-3" />} color="green" />
                            <Stat label={mix.camelot ? "KEY" : "PLAYS"} value={mix.camelot || mix.play_count || 0} icon={<Headphones className="w-3 h-3" />} />
                        </div>
                        <button
                            onClick={onPlayAll}
                            disabled={!playable}
                            data-testid="play-mix-button"
                            className="w-full mt-2 bg-neon-cyan text-black font-display font-black tracking-widest uppercase py-3 hover:bg-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center gap-2 shadow-[0_0_20px_rgba(0,240,255,0.4)]"
                        >
                            {isCurrent && player.playing ? (
                                <><Pause className="w-4 h-4 fill-current" /> PAUSE MIX</>
                            ) : (
                                <><Play className="w-4 h-4 fill-current" /> PLAY MIX</>
                            )}
                        </button>
                    </div>
                </div>

                {/* CENTER: deck */}
                <div className="lg:col-span-8 space-y-4">
                    <div className="border border-[#1A1D2E] bg-[#0a0c14] relative scanlines">
                        <div className="px-4 py-2 border-b border-[#1A1D2E] flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-neon-red animate-pulse" />
                                <span className="label text-neon-red">REC</span>
                                <span className="label text-zinc-500">// CHANNEL A</span>
                            </div>
                            <span className="label text-neon-cyan">DECK 01</span>
                        </div>
                        <div className="p-4 space-y-3">
                            <Waveform
                                mixId={mix.id}
                                currentTime={time}
                                duration={dur}
                                onSeek={onSeek}
                                tracks={mix.tracks}
                                height={120}
                            />
                            <div className="flex items-center justify-between text-xs font-mono">
                                <span className="text-neon-green glow-green">{fmtTime(time)}</span>
                                <span className="text-zinc-500">{fmtTime(dur)}</span>
                            </div>

                            {/* Transport */}
                            <div className="flex items-center justify-center gap-3 pt-2">
                                <ControlBtn onClick={() => player.seekRelative(-30)} aria="back-30">
                                    <SkipBack className="w-5 h-5" />
                                </ControlBtn>
                                <button
                                    onClick={onPlayAll}
                                    disabled={!playable}
                                    data-testid="deck-play-pause"
                                    className={`w-16 h-16 rounded-full bg-neon-cyan text-black flex items-center justify-center shadow-[0_0_28px_rgba(0,240,255,0.6)] hover:scale-105 transition-transform ${
                                        isCurrent && player.playing ? "" : "animate-pulse-glow"
                                    }`}
                                    aria-label="Play"
                                >
                                    {isCurrent && player.playing ? (
                                        <Pause className="w-6 h-6 fill-current" />
                                    ) : (
                                        <Play className="w-6 h-6 fill-current ml-0.5" />
                                    )}
                                </button>
                                <ControlBtn onClick={() => player.seekRelative(30)} aria="fwd-30">
                                    <SkipForward className="w-5 h-5" />
                                </ControlBtn>

                                <div className="ml-4 hidden md:flex items-center gap-2">
                                    <button
                                        onClick={() => player.setMuted(!player.muted)}
                                        className="text-zinc-400 hover:text-neon-cyan"
                                        aria-label="Mute"
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
                                        className="w-28"
                                        style={{ "--seek": `${player.volume * 100}%` }}
                                    />
                                </div>
                            </div>

                            {/* VU meters */}
                            <div className="grid grid-cols-2 gap-3 pt-3 border-t border-[#1A1D2E]">
                                <div className="flex items-center gap-2">
                                    <span className="label">L</span>
                                    <div className="h-4 flex-1"><VuMeter orientation="horizontal" label="L" /></div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className="label">R</span>
                                    <div className="h-4 flex-1"><VuMeter orientation="horizontal" label="R" /></div>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Tracklist */}
                    <CueTrackList tracks={mix.tracks || []} currentIndex={trackIndex} onJump={onSeek} />
                </div>
            </div>
        </div>
    );
};

const Stat = ({ label, value, icon, color = "cyan" }) => (
    <div className="border border-[#1A1D2E] p-2.5">
        <div className="label flex items-center gap-1">{icon} {label}</div>
        <div className={`font-display font-bold text-base mt-1 ${color === "green" ? "text-neon-green" : "text-neon-cyan"}`}>
            {value}
        </div>
    </div>
);

const ControlBtn = ({ children, onClick, aria }) => (
    <button
        onClick={onClick}
        data-testid={`ctl-${aria}`}
        className="w-11 h-11 border border-[#1A1D2E] hover:border-neon-cyan hover:text-neon-cyan text-zinc-300 flex items-center justify-center transition-colors"
        aria-label={aria}
    >
        {children}
    </button>
);
