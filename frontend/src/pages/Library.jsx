import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { api, BACKEND_URL } from "../lib/api";
import { MixCard } from "../components/MixCard";
import { Disc3, Radio, Loader2, Rss, Hash } from "lucide-react";

export const Library = ({ search = "" }) => {
    const [searchParams, setSearchParams] = useSearchParams();
    const [mixes, setMixes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [genre, setGenre] = useState("");
    const [tag, setTag] = useState(searchParams.get("tag") || "");
    const [genres, setGenres] = useState([]);
    const [tags, setTags] = useState([]);

    // Sync the ?tag= URL param with state so /mix detail tag links pre-filter the library
    useEffect(() => {
        const urlTag = searchParams.get("tag") || "";
        if (urlTag !== tag) setTag(urlTag);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [searchParams]);

    const setTagAndUrl = (newTag) => {
        setTag(newTag);
        const next = new URLSearchParams(searchParams);
        if (newTag) next.set("tag", newTag);
        else next.delete("tag");
        setSearchParams(next, { replace: true });
    };

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const data = await api.listMixes(search, genre, tag);
            setMixes(data);
            const g = await api.listGenres();
            setGenres(g.genres || []);
            const t = await api.listTags();
            setTags(t.tags || []);
        } finally {
            setLoading(false);
        }
    }, [search, genre, tag]);

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
                    <a
                        href={`${BACKEND_URL}/api/feed.xml`}
                        target="_blank"
                        rel="noreferrer"
                        data-testid="rss-subscribe-link"
                        className="mt-5 inline-flex items-center gap-2 px-4 py-2 border border-neon-cyan/40 text-neon-cyan label hover:bg-neon-cyan/10 transition-colors"
                    >
                        <Rss className="w-3.5 h-3.5" /> SUBSCRIBE · RSS PODCAST FEED
                    </a>
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

            {/* Tag chip cloud (AI-generated mood/vibe tags) */}
            {tags.length > 0 && (
                <div className="mb-6 flex items-start gap-2.5" data-testid="tag-filters">
                    <Hash className="w-3.5 h-3.5 text-neon-green shrink-0 mt-1.5" />
                    <div className="flex flex-wrap gap-1.5">
                        {tag && (
                            <button
                                onClick={() => setTagAndUrl("")}
                                data-testid="tag-clear"
                                className="label px-2 py-1 border border-neon-red/40 text-neon-red bg-neon-red/5 hover:bg-neon-red/15 transition-colors"
                            >
                                CLEAR ×
                            </button>
                        )}
                        {tags.slice(0, 30).map((t) => (
                            <button
                                key={t.tag}
                                onClick={() => setTagAndUrl(t.tag === tag ? "" : t.tag)}
                                data-testid={`tag-chip-${t.tag}`}
                                title={`${t.count} mix${t.count === 1 ? "" : "es"}`}
                                className={`label px-2 py-1 border transition-colors ${
                                    tag === t.tag
                                        ? "border-neon-green text-neon-green bg-neon-green/10 shadow-[0_0_10px_rgba(57,255,20,0.3)]"
                                        : "border-[#1A1D2E] text-zinc-400 hover:text-neon-green hover:border-neon-green/40"
                                }`}
                            >
                                {t.tag} <span className="text-zinc-600 ml-1">{t.count}</span>
                            </button>
                        ))}
                    </div>
                </div>
            )}

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
