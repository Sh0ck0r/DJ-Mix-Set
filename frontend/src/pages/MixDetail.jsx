import { useEffect, useState, useRef } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import { api, coverUrl, fmtTime, parseTimeStamp, shareUrl, getResumePosition, clearResumePosition } from "../lib/api";
import { usePlayer } from "../contexts/PlayerContext";
import { CueTrackList } from "../components/CueTrackList";
import { DjConsole } from "../components/dj/DjConsole";
import { CompatibleMixesRow } from "../components/CompatibleMixesRow";
import {
    Play, Pause, ArrowLeft, Music, Clock, Activity, Headphones, Loader2, Share2, Check, RotateCcw, X,
} from "lucide-react";
import { toast } from "sonner";

export const MixDetail = () => {
    const { id } = useParams();
    const [searchParams] = useSearchParams();
    const [mix, setMix] = useState(null);
    const [loading, setLoading] = useState(true);
    const [shared, setShared] = useState(false);
    const [resume, setResume] = useState(null);
    const deepSeekApplied = useRef(false);
    const player = usePlayer();
    const isCurrent = player.mix?.id === id;

    useEffect(() => {
        let alive = true;
        setLoading(true);
        api.getMix(id).then((m) => {
            if (alive) {
                setMix(m);
                setLoading(false);
                // Surface resume position only if there's no ?t= param (deep-seek wins)
                if (!searchParams.get("t")) {
                    setResume(getResumePosition(id));
                }
            }
        }).catch(() => setLoading(false));
        return () => {
            alive = false;
        };
    }, [id, searchParams]);

    // Deep-seek from URL ?t=12:34 - applies once after mix + audio is ready.
    const playable = !!(mix?.audio_filename || mix?.audio_url || mix?.source_path);
    useEffect(() => {
        if (!mix || deepSeekApplied.current) return;
        const raw = searchParams.get("t");
        const target = parseTimeStamp(raw);
        if (target == null || !playable) return;
        deepSeekApplied.current = true;
        player.loadMix(mix);
        const tryThis = (attempts = 0) => {
            if (player.audioRef.current?.duration) {
                player.seek(target);
            } else if (attempts < 30) {
                setTimeout(() => tryThis(attempts + 1), 200);
            }
        };
        setTimeout(() => tryThis(), 300);
    }, [mix, playable, searchParams, player]);

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

    const onShare = async () => {
        const t = isCurrent ? Math.floor(player.currentTime) : 0;
        const url = shareUrl(id, t);
        try {
            await navigator.clipboard.writeText(url);
            setShared(true);
            toast.success("LINK COPIED", {
                description: t > 0 ? `Jumps straight to ${fmtTime(t)} · rich preview ready` : "Mix link in clipboard · rich preview ready",
            });
            setTimeout(() => setShared(false), 2000);
        } catch {
            toast.error("Couldn't access clipboard");
        }
    };

    const onResume = () => {
        if (!resume || !mix) return;
        player.loadMix(mix);
        const t = resume.t;
        setResume(null);
        const trySeek = (attempts = 0) => {
            if (player.audioRef.current?.duration) {
                player.seek(t);
            } else if (attempts < 30) {
                setTimeout(() => trySeek(attempts + 1), 200);
            }
        };
        setTimeout(trySeek, 300);
    };

    const onDismissResume = () => {
        clearResumePosition(id);
        setResume(null);
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
            {resume && playable && !isCurrent && (
                <div
                    data-testid="resume-banner"
                    className="border border-neon-green/40 bg-neon-green/5 p-3 flex items-center gap-3 mb-6 scanlines relative"
                >
                    <RotateCcw className="w-4 h-4 text-neon-green shrink-0" />
                    <div className="flex-1 min-w-0">
                        <div className="font-display font-bold text-sm text-neon-green tracking-wider">
                            RESUME WHERE YOU LEFT OFF
                        </div>
                        <div className="font-mono text-xs text-zinc-400 mt-0.5">
                            You stopped at <span className="text-neon-green">{fmtTime(resume.t)}</span> · pick up the vibe?
                        </div>
                    </div>
                    <button
                        onClick={onResume}
                        data-testid="resume-button"
                        className="bg-neon-green text-black font-display font-black tracking-widest uppercase px-3 py-1.5 hover:bg-white transition-colors shadow-[0_0_15px_rgba(57,255,20,0.4)] flex items-center gap-1.5"
                    >
                        <Play className="w-3.5 h-3.5 fill-current" /> RESUME
                    </button>
                    <button
                        onClick={onDismissResume}
                        data-testid="dismiss-resume"
                        title="Start from the beginning"
                        className="text-zinc-500 hover:text-neon-red transition-colors"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
            )}
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
                        {mix.tags && mix.tags.length > 0 && (
                            <div className="flex flex-wrap gap-1.5" data-testid="mix-tags">
                                {mix.tags.map((t) => (
                                    <Link
                                        key={t}
                                        to={`/?tag=${encodeURIComponent(t)}`}
                                        data-testid={`mix-tag-${t}`}
                                        className="label px-2 py-0.5 border border-neon-green/40 text-neon-green bg-neon-green/5 hover:bg-neon-green/15 transition-colors"
                                    >
                                        # {t}
                                    </Link>
                                ))}
                            </div>
                        )}
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
                        <button
                            onClick={onShare}
                            data-testid="share-mix-button"
                            className="w-full mt-2 bg-transparent text-neon-cyan font-display font-bold tracking-widest uppercase py-2.5 border border-neon-cyan/40 hover:bg-neon-cyan/10 transition-colors flex items-center justify-center gap-2"
                            title={isCurrent && player.currentTime > 0 ? `Share with timestamp ${fmtTime(Math.floor(player.currentTime))}` : "Share mix link"}
                        >
                            {shared ? <Check className="w-4 h-4" /> : <Share2 className="w-4 h-4" />}
                            {shared ? "COPIED" : (isCurrent && player.currentTime > 0 ? `SHARE @ ${fmtTime(Math.floor(player.currentTime))}` : "SHARE LINK")}
                        </button>
                    </div>
                </div>

                {/* CENTER: DJ CONSOLE */}
                <div className="lg:col-span-8 space-y-4">
                    <DjConsole
                        mix={mix}
                        isCurrent={isCurrent}
                        onPlayToggle={onPlayAll}
                        onSeek={onSeek}
                    />
                    {/* Full tracklist */}
                    <CueTrackList tracks={mix.tracks || []} currentIndex={trackIndex} onJump={onSeek} />
                    {/* Harmonic recommendations */}
                    <CompatibleMixesRow mixId={mix.id} />
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
