import { fmtTime } from "../lib/api";
import { Disc3, Activity } from "lucide-react";

export const CueTrackList = ({ tracks = [], currentIndex = -1, onJump, dense = false }) => {
    if (!tracks.length) {
        return (
            <div className="border border-[#1A1D2E] p-6 text-center">
                <Disc3 className="w-8 h-8 mx-auto text-zinc-700 mb-2" strokeWidth={1.2} />
                <p className="label">NO CUE SHEET PROVIDED</p>
            </div>
        );
    }
    const analyzed = tracks.some((t) => t.bpm || t.key);
    return (
        <div className="border border-[#1A1D2E] divide-y divide-[#1A1D2E]" data-testid="cue-tracklist">
            <div className="px-3 py-2 flex items-center justify-between bg-[#0a0c14]">
                <span className="label">CUE SHEET // TRACKLIST</span>
                <span className="label text-neon-cyan flex items-center gap-2">
                    {analyzed && (
                        <span className="flex items-center gap-1 text-neon-green">
                            <Activity className="w-3 h-3" /> ANALYZED
                        </span>
                    )}
                    {tracks.length} TRX
                </span>
            </div>
            <div className={dense ? "max-h-72 overflow-auto" : "max-h-[55vh] overflow-auto"}>
                {tracks.map((tr, i) => {
                    const active = i === currentIndex;
                    return (
                        <button
                            key={i}
                            data-testid="cue-track-item"
                            onClick={() => onJump?.(tr.start_seconds)}
                            className={`w-full text-left px-3 py-2.5 grid grid-cols-[auto_1fr_auto_auto] gap-3 items-center transition-all duration-150 ${
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
                        </button>
                    );
                })}
            </div>
        </div>
    );
};
