import { fmtTime } from "../../lib/api";

// 8 performance pads that jump to the first 8 tracks in the cue.
// Colors cycle through a DJ palette, tinted by Camelot key if available.
const PAD_COLORS = [
    "#00F0FF", // cyan
    "#39FF14", // green
    "#FF9D00", // orange
    "#FF003C", // red
    "#C800FF", // magenta
    "#FFE500", // yellow
    "#00FF9D", // mint
    "#0088FF", // blue
];

const KEY_COLORS = {
    A: "#00F0FF", B: "#39FF14",
};

function padColor(track, idx) {
    if (track?.camelot) {
        const mode = track.camelot.slice(-1);
        return KEY_COLORS[mode] || PAD_COLORS[idx % PAD_COLORS.length];
    }
    return PAD_COLORS[idx % PAD_COLORS.length];
}

export const PerformancePads = ({ tracks = [], currentIndex = -1, onJump }) => {
    const pads = Array.from({ length: 8 }, (_, i) => tracks[i]);

    return (
        <div className="grid grid-cols-4 md:grid-cols-8 gap-2" data-testid="performance-pads">
            {pads.map((tr, i) => {
                const color = tr ? padColor(tr, i) : "#1a1d2e";
                const active = i === currentIndex;
                const hasTrack = !!tr;
                return (
                    <button
                        key={i}
                        disabled={!hasTrack}
                        onClick={() => hasTrack && onJump?.(tr.start_seconds)}
                        data-testid={`pad-${i + 1}`}
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
                                    {String(i + 1).padStart(2, "0")}
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
    );
};
