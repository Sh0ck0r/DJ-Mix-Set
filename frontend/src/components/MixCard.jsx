import { Link } from "react-router-dom";
import { Play, Music, Headphones } from "lucide-react";
import { coverUrl, fmtTime } from "../lib/api";
import { usePlayer } from "../contexts/PlayerContext";

const FALLBACK_COVERS = [
    "https://images.unsplash.com/photo-1769120061986-a077f35b2569?w=600&q=80",
    "https://images.unsplash.com/photo-1769120062656-23adba3790b3?w=600&q=80",
];

export const MixCard = ({ mix, index = 0 }) => {
    const { loadMix } = usePlayer();
    const cover = coverUrl(mix) || FALLBACK_COVERS[index % FALLBACK_COVERS.length];
    const playable = !!(mix.audio_filename || mix.audio_url);

    const onPlay = (e) => {
        e.preventDefault();
        if (playable) loadMix(mix);
    };

    return (
        <Link
            to={`/mix/${mix.id}`}
            data-testid="mix-card"
            className="group relative block bg-[#0D0E15] border border-[#1A1D2E] hover:border-neon-cyan/60 transition-all duration-150 hover:-translate-y-0.5 hover:shadow-[0_0_30px_rgba(0,240,255,0.25)]"
        >
            <div className="relative aspect-square overflow-hidden bg-black">
                <img
                    src={cover}
                    alt={mix.title}
                    className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                    loading="lazy"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent" />
                <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity backdrop-blur-[2px] flex items-center justify-center">
                    {playable ? (
                        <button
                            onClick={onPlay}
                            data-testid="card-play-button"
                            className="w-14 h-14 rounded-full bg-neon-cyan text-black flex items-center justify-center hover:scale-110 transition-transform shadow-[0_0_28px_rgba(0,240,255,0.8)]"
                            aria-label="Play"
                        >
                            <Play className="w-6 h-6 fill-current ml-0.5" />
                        </button>
                    ) : (
                        <span className="label text-zinc-500">NO AUDIO</span>
                    )}
                </div>
                <div className="absolute top-2 left-2 flex gap-1">
                    {mix.bpm ? (
                        <span className="label bg-black/70 px-1.5 py-0.5 text-neon-green border border-neon-green/30">
                            {mix.bpm} BPM
                        </span>
                    ) : null}
                </div>
                {mix.duration ? (
                    <span className="absolute bottom-2 right-2 label bg-black/70 px-1.5 py-0.5 text-neon-cyan border border-neon-cyan/30">
                        {fmtTime(mix.duration)}
                    </span>
                ) : null}
            </div>
            <div className="p-3 space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                    <h3 className="font-display font-bold text-sm text-white truncate group-hover:text-neon-cyan transition-colors">
                        {mix.title}
                    </h3>
                </div>
                <p className="font-mono text-xs text-zinc-500 truncate flex items-center gap-1.5">
                    <Music className="w-3 h-3" />
                    {mix.artist || "UNKNOWN ARTIST"}
                </p>
                <div className="flex items-center justify-between pt-1.5 border-t border-[#1A1D2E]">
                    <span className="label">{mix.genre || "MIX"}</span>
                    <span className="label flex items-center gap-1 text-zinc-500">
                        <Headphones className="w-3 h-3" />
                        {mix.play_count || 0}
                    </span>
                </div>
            </div>
        </Link>
    );
};
