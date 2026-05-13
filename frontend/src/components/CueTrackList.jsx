import { useMemo, useState } from "react";
import { fmtTime, api } from "../lib/api";
import { Disc3, Activity, Search, X, Mic, Loader2 } from "lucide-react";
import { toast } from "sonner";

export const CueTrackList = ({ tracks = [], currentIndex = -1, onJump, dense = false, mixId, isAdmin = false }) => {
    const [query, setQuery] = useState("");
    const [transcribingIdx, setTranscribingIdx] = useState(-1);

    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return tracks.map((t, i) => ({ tr: t, i }));
        return tracks
            .map((t, i) => ({ tr: t, i }))
            .filter(({ tr }) => {
                const hay = [
                    tr.title,
                    tr.artist,
                    tr.bpm ? String(tr.bpm) : "",
                    tr.camelot,
                    tr.key,
                ]
                    .filter(Boolean)
                    .join(" ")
                    .toLowerCase();
                return hay.includes(q);
            });
    }, [tracks, query]);

    const transcribe = async (e, idx, tr) => {
        e.stopPropagation();
        if (transcribingIdx !== -1) return;
        setTranscribingIdx(idx);
        try {
            const res = await api.transcribeTrack(mixId, idx);
            toast.success(`WHISPER · ${res.lines} LINES`, {
                description: `${res.source.toUpperCase()} · ${tr.artist || ""} — ${tr.title || ""}`.trim(),
            });
        } catch (err) {
            const detail = err.response?.data?.detail || err.message || "Transcription failed";
            toast.error("WHISPER FAILED", { description: detail });
        } finally {
            setTranscribingIdx(-1);
        }
    };

    if (!tracks.length) {
        return (
            <div className="border border-[#1A1D2E] p-6 text-center">
                <Disc3 className="w-8 h-8 mx-auto text-zinc-700 mb-2" strokeWidth={1.2} />
                <p className="label">NO CUE SHEET PROVIDED</p>
            </div>
        );
    }
    const analyzed = tracks.some((t) => t.bpm || t.key);
    const showSearch = tracks.length > 8;

    return (
        <div className="border border-[#1A1D2E] divide-y divide-[#1A1D2E]" data-testid="cue-tracklist">
            <div className="px-3 py-2 flex items-center justify-between bg-[#0a0c14] gap-3">
                <span className="label shrink-0">CUE SHEET // TRACKLIST</span>
                {showSearch && (
                    <div className="relative flex-1 max-w-xs">
                        <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
                        <input
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder="SEARCH TRACKS · ARTIST · BPM · KEY"
                            data-testid="tracklist-search"
                            className="w-full bg-black border border-[#1A1D2E] focus:border-neon-cyan focus:outline-none pl-7 pr-7 py-1.5 text-white font-mono text-xs uppercase tracking-wider placeholder:text-zinc-600"
                        />
                        {query && (
                            <button
                                onClick={() => setQuery("")}
                                data-testid="tracklist-search-clear"
                                className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-neon-red"
                                aria-label="Clear search"
                            >
                                <X className="w-3 h-3" />
                            </button>
                        )}
                    </div>
                )}
                <span className="label text-neon-cyan flex items-center gap-2 shrink-0">
                    {analyzed && (
                        <span className="flex items-center gap-1 text-neon-green">
                            <Activity className="w-3 h-3" /> ANALYZED
                        </span>
                    )}
                    <span data-testid="tracklist-count">
                        {query ? `${filtered.length}/${tracks.length}` : `${tracks.length} TRX`}
                    </span>
                </span>
            </div>
            <div className={dense ? "max-h-72 overflow-auto" : "max-h-[55vh] overflow-auto"}>
                {filtered.length === 0 ? (
                    <div className="px-3 py-8 text-center label text-zinc-500">
                        NO TRACKS MATCH "{query}"
                    </div>
                ) : (
                    filtered.map(({ tr, i }) => {
                        const active = i === currentIndex;
                        const isTranscribing = transcribingIdx === i;
                        const gridCols = isAdmin && mixId ? "grid-cols-[auto_1fr_auto_auto_auto]" : "grid-cols-[auto_1fr_auto_auto]";
                        return (
                            <button
                                key={i}
                                data-testid="cue-track-item"
                                onClick={() => onJump?.(tr.start_seconds)}
                                className={`w-full text-left px-3 py-2.5 grid ${gridCols} gap-3 items-center transition-all duration-150 ${
                                    active
                                        ? "bg-neon-cyan/10 border-l-2 border-neon-cyan"
                                        : "border-l-2 border-transparent hover:bg-white/5 hover:border-neon-cyan/40"
                                }`}
                            >
                                <span className={`font-mono text-xs ${active ? "text-neon-cyan" : "text-zinc-600"}`}>
                                    {String(i + 1).padStart(2, "0")}
                                </span>
                                <div className="min-w-0">
                                    <div className={`font-ui text-sm truncate ${active ? "text-white glow-cyan" : "text-zinc-200"}`}>
                                        {tr.title || "Untitled"}
                                    </div>
                                    {tr.artist ? (
                                        <div className="font-mono text-[11px] truncate text-zinc-500">{tr.artist}</div>
                                    ) : null}
                                </div>
                                <div className="flex items-center gap-1.5 shrink-0">
                                    {tr.bpm ? (
                                        <span className="label px-1.5 py-0.5 border border-neon-green/40 text-neon-green">
                                            {tr.bpm}
                                        </span>
                                    ) : null}
                                    {tr.camelot ? (
                                        <span className="label px-1.5 py-0.5 border border-neon-cyan/40 text-neon-cyan" title={tr.key || ""}>
                                            {tr.camelot}
                                        </span>
                                    ) : null}
                                </div>
                                <span className={`font-mono text-xs tabular-nums ${active ? "text-neon-green glow-green" : "text-zinc-500"}`}>
                                    {fmtTime(tr.start_seconds)}
                                </span>
                                {isAdmin && mixId && (
                                    <span
                                        role="button"
                                        tabIndex={0}
                                        onClick={(e) => transcribe(e, i, tr)}
                                        onKeyDown={(e) => {
                                            if (e.key === "Enter" || e.key === " ") transcribe(e, i, tr);
                                        }}
                                        data-testid={`whisper-transcribe-${i}`}
                                        title={`Re-transcribe with local Whisper (skips last transition seconds)`}
                                        aria-label="Re-transcribe with Whisper"
                                        className={`shrink-0 p-1 cursor-pointer transition-colors ${
                                            isTranscribing
                                                ? "text-neon-green"
                                                : "text-zinc-600 hover:text-neon-green"
                                        } ${transcribingIdx !== -1 && !isTranscribing ? "opacity-30 pointer-events-none" : ""}`}
                                    >
                                        {isTranscribing ? (
                                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                        ) : (
                                            <Mic className="w-3.5 h-3.5" />
                                        )}
                                    </span>
                                )}
                            </button>
                        );
                    })
                )}
            </div>
        </div>
    );
};
