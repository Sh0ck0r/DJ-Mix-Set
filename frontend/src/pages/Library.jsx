import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import { MixCard } from "../components/MixCard";
import { Disc3, Radio, Loader2 } from "lucide-react";

export const Library = ({ search = "" }) => {
    const [mixes, setMixes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [genre, setGenre] = useState("");
    const [genres, setGenres] = useState([]);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const data = await api.listMixes(search, genre);
            setMixes(data);
            const g = await api.listGenres();
            setGenres(g.genres || []);
        } finally {
            setLoading(false);
        }
    }, [search, genre]);

    useEffect(() => {
        // seed-demo on first visit so user has something to see
        api.seedDemo().catch(() => {}).finally(() => {
            load();
        });
    }, [load]);

    return (
        <div className="max-w-[1600px] mx-auto px-4 md:px-8 py-8 md:py-12">
            {/* Hero */}
            <section className="relative mb-12 md:mb-16 overflow-hidden border border-[#1A1D2E]">
                <div className="absolute inset-0 grid-bg opacity-40" />
                <div
                    className="absolute inset-0 bg-cover bg-center opacity-25"
                    style={{
                        backgroundImage:
                            "url(https://images.unsplash.com/photo-1642784352095-f317a1b58f35?w=1600&q=85)",
                    }}
                />
                <div className="absolute inset-0 bg-gradient-to-r from-[#050505] via-[#050505]/80 to-transparent" />
                <div className="relative px-6 md:px-12 py-16 md:py-24 max-w-3xl">
                    <div className="flex items-center gap-2 mb-6">
                        <Radio className="w-4 h-4 text-neon-cyan animate-pulse" />
                        <span className="label text-neon-cyan">// LIVE FROM THE DECK</span>
                    </div>
                    <h1 className="font-display font-black text-4xl sm:text-5xl lg:text-6xl tracking-tight uppercase leading-[0.95] text-white">
                        NONSTOP <span className="text-neon-cyan glow-cyan">MIXES</span>
                        <br />
                        FOR THE <span className="text-neon-green glow-green">NIGHT</span>
                    </h1>
                    <p className="mt-6 font-mono text-sm md:text-base text-zinc-400 max-w-xl leading-relaxed">
                        A digitized cabinet for your DJ sets. Drop a CUE sheet, get a synced tracklist.
                        Hit play — let the waveform roll.
                    </p>
                </div>
            </section>

            {/* Filters */}
            <div className="flex items-center justify-between mb-6 gap-4 flex-wrap">
                <div className="flex items-center gap-3">
                    <Disc3 className="w-5 h-5 text-neon-cyan" />
                    <h2 className="font-display font-bold text-lg uppercase tracking-widest">
                        Mix Library <span className="text-neon-cyan">{mixes.length}</span>
                    </h2>
                </div>
                {genres.length > 0 && (
                    <div className="flex items-center gap-2 overflow-x-auto" data-testid="genre-filters">
                        <button
                            onClick={() => setGenre("")}
                            className={`label px-3 py-1.5 border whitespace-nowrap transition-colors ${
                                !genre
                                    ? "border-neon-cyan text-neon-cyan bg-neon-cyan/10"
                                    : "border-[#1A1D2E] text-zinc-500 hover:text-white"
                            }`}
                        >
                            ALL
                        </button>
                        {genres.map((g) => (
                            <button
                                key={g}
                                onClick={() => setGenre(g === genre ? "" : g)}
                                className={`label px-3 py-1.5 border whitespace-nowrap transition-colors ${
                                    genre === g
                                        ? "border-neon-cyan text-neon-cyan bg-neon-cyan/10"
                                        : "border-[#1A1D2E] text-zinc-500 hover:text-white"
                                }`}
                            >
                                {g}
                            </button>
                        ))}
                    </div>
                )}
            </div>

            {/* Grid */}
            {loading ? (
                <div className="py-20 flex items-center justify-center">
                    <Loader2 className="w-8 h-8 text-neon-cyan animate-spin" />
                </div>
            ) : mixes.length === 0 ? (
                <div className="border border-dashed border-[#1A1D2E] p-12 text-center">
                    <Disc3 className="w-12 h-12 mx-auto text-zinc-700 mb-4" strokeWidth={1.2} />
                    <p className="label mb-2">NO MIXES YET</p>
                    <p className="font-mono text-sm text-zinc-500">
                        Sign in as admin and upload your first set.
                    </p>
                </div>
            ) : (
                <div
                    data-testid="mix-grid"
                    className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4 md:gap-6"
                >
                    {mixes.map((m, i) => (
                        <MixCard key={m.id} mix={m} index={i} />
                    ))}
                </div>
            )}
        </div>
    );
};
