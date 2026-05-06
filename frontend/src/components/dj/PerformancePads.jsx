import { useEffect, useMemo, useState } from "react";
import { fmtTime } from "../../lib/api";
import { ChevronLeft, ChevronRight } from "lucide-react";

// 8 performance pads that jump to tracks in the cue. Paginated so 100+ track
// mixes can hot-cue every track, not just the first 8.
const PAD_COLORS = [
    "#00F0FF", "#39FF14", "#FF9D00", "#FF003C",
    "#C800FF", "#FFE500", "#00FF9D", "#0088FF",
];
const KEY_COLORS = { A: "#00F0FF", B: "#39FF14" };
const PADS_PER_PAGE = 8;

function padColor(track, idx) {
    if (track?.camelot) {
        const mode = track.camelot.slice(-1);
        return KEY_COLORS[mode] || PAD_COLORS[idx % PAD_COLORS.length];
    }
    return PAD_COLORS[idx % PAD_COLORS.length];
}

export const PerformancePads = ({ tracks = [], currentIndex = -1, onJump }) => {
    const totalPages = Math.max(1, Math.ceil(tracks.length / PADS_PER_PAGE));
    const [page, setPage] = useState(0);

    // Auto-flip to the page that contains the current track when it changes
    useEffect(() => {
        if (currentIndex < 0) return;
        const targetPage = Math.floor(currentIndex / PADS_PER_PAGE);
        if (targetPage !== page) setPage(targetPage);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [currentIndex]);

    const startIdx = page * PADS_PER_PAGE;
    const pads = useMemo(
        () => Array.from({ length: PADS_PER_PAGE }, (_, i) => tracks[startIdx + i]),
        [tracks, startIdx]
    );
    const showPager = totalPages > 1;
    const last = totalPages - 1;

    return (
        <div className="space-y-2" data-testid="performance-pads-wrapper">
            {showPager && (
                <div className="flex items-center justify-between" data-testid="pads-pager">
                    <button
                        onClick={() => setPage((p) => Math.max(0, p - 1))}
                        disabled={page === 0}
                        data-testid="pads-prev"
                        className="label flex items-center gap-1 px-2 py-1 border border-[#1A1D2E] hover:border-neon-cyan hover:text-neon-cyan transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                        <ChevronLeft className="w-3 h-3" /> PREV
                    </button>
                    <div className="flex items-center gap-2">
                        <span className="label text-zinc-500" data-testid="pads-page-label">
                            BANK <span className="text-neon-cyan">{page + 1}</span>/{totalPages} ·
                            TRX {startIdx + 1}-{Math.min(startIdx + PADS_PER_PAGE, tracks.length)}/{tracks.length}
                        </span>
                        {/* page-dots */}
                        <div className="hidden md:flex items-center gap-1 ml-2">
                            {Array.from({ length: Math.min(totalPages, 12) }).map((_, i) => {
                                const isCurrent = i === page;
                                const containsActive = currentIndex >= 0
                                    && Math.floor(currentIndex / PADS_PER_PAGE) === i;
                                return (
                                    <button
                                        key={i}
                                        onClick={() => setPage(i)}
                                        title={`Bank ${i + 1}`}
                                        className={`w-1.5 h-1.5 rounded-full transition-all ${
                                            isCurrent ? "bg-neon-cyan scale-150" :
                                            containsActive ? "bg-neon-green" :
                                            "bg-zinc-700 hover:bg-zinc-500"
                                        }`}
                                    />
                                );
                            })}
                            {totalPages > 12 && <span className="label text-zinc-600 ml-1">+{totalPages - 12}</span>}
                        </div>
                    </div>
                    <button
                        onClick={() => setPage((p) => Math.min(last, p + 1))}
                        disabled={page === last}
                        data-testid="pads-next"
                        className="label flex items-center gap-1 px-2 py-1 border border-[#1A1D2E] hover:border-neon-cyan hover:text-neon-cyan transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                        NEXT <ChevronRight className="w-3 h-3" />
                    </button>
                </div>
            )}
            <div className="grid grid-cols-4 md:grid-cols-8 gap-2" data-testid="performance-pads">
                {pads.map((tr, i) => {
                    const trackIndex = startIdx + i;
                    const color = tr ? padColor(tr, trackIndex) : "#1a1d2e";
                    const active = trackIndex === currentIndex;
                    const hasTrack = !!tr;
                    return (
                        <button
                            key={trackIndex}
                            disabled={!hasTrack}
                            onClick={() => hasTrack && onJump?.(tr.start_seconds)}
                            data-testid={`pad-${trackIndex + 1}`}
                            className={`relative group aspect-square border transition-all duration-150 ${
                                hasTrack
                                    ? "border-[#1A1D2E] hover:scale-[1.03] active:scale-95 cursor-pointer"
                                    : "border-[#1A1D2E]/40 cursor-not-allowed"
                            }`}
                            style={{
                                background: hasTrack
                                    ? active
                                        ? `linear-gradient(135deg, ${color}, ${color}55)`
                                        : `linear-gradient(135deg, ${color}20, ${color}05)`
                                    : "#0a0c14",
                                boxShadow: active
                                    ? `0 0 20px ${color}, inset 0 0 20px ${color}66`
                                    : hasTrack
                                        ? `inset 0 0 15px ${color}15`
                                        : "none",
                            }}
                        >
                            {hasTrack && (
                                <>
                                    <div
                                        className="absolute top-1.5 left-1.5 label font-bold"
                                        style={{ color, fontSize: 10 }}
                                    >
                                        {String(trackIndex + 1).padStart(2, "0")}
                                    </div>
                                    {tr.camelot && (
                                        <div
                                            className="absolute top-1.5 right-1.5 label font-bold"
                                            style={{ color, fontSize: 10 }}
                                        >
                                            {tr.camelot}
                                        </div>
                                    )}
                                    <div className="absolute inset-x-1.5 bottom-1.5 flex items-end justify-between">
                                        <div className="text-left min-w-0 flex-1">
                                            <div className="font-ui text-[10px] text-white truncate leading-tight">
                                                {tr.title}
                                            </div>
                                            <div className="font-mono text-[9px] text-white/60">
                                                {fmtTime(tr.start_seconds)}
                                                {tr.bpm ? ` · ${tr.bpm}` : ""}
                                            </div>
                                        </div>
                                    </div>
                                    {active && (
                                        <div
                                            className="absolute inset-0 border-2"
                                            style={{ borderColor: color, boxShadow: `0 0 16px ${color}` }}
                                        />
                                    )}
                                </>
                            )}
                        </button>
                    );
                })}
            </div>
        </div>
    );
};
