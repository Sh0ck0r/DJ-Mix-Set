import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, coverUrl, fmtTime } from "../lib/api";
import { Disc3, Activity, Loader2 } from "lucide-react";

export const CompatibleMixesRow = ({ mixId }) => {
    const [mixes, setMixes] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let alive = true;
        setLoading(true);
        api.compatibleMixes(mixId, 8)
            .then((data) => {
                if (alive) setMixes(data);
            })
            .catch(() => {})
            .finally(() => {
                if (alive) setLoading(false);
            });
        return () => {
            alive = false;
        };
    }, [mixId]);

    if (loading) {
        return (
            <div className="border border-[#1A1D2E] p-6 flex items-center justify-center">
                <Loader2 className="w-5 h-5 animate-spin text-neon-cyan" />
            </div>
        );
    }
    if (!mixes.length) return null;

    return (
        <div className="border border-[#1A1D2E] bg-[#0a0c14]" data-testid="compatible-mixes">
            <div className="px-4 py-2 border-b border-[#1A1D2E] flex items-center justify-between bg-black/40">
                <div className="flex items-center gap-2">
                    <Activity className="w-4 h-4 text-neon-cyan" />
                    <span className="label text-neon-cyan">// MORE LIKE THIS</span>
                </div>
                <span className="label text-zinc-500">SAME ENERGY · ADJACENT KEY · SHARED TAGS</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 p-4">
                {mixes.map((m) => (
                    <Link
                        key={m.id}
                        to={`/mix/${m.id}`}
                        data-testid="compatible-mix-card"
                        className="group flex items-center gap-3 border border-[#1A1D2E] bg-black/30 hover:border-neon-cyan/60 hover:shadow-[0_0_20px_rgba(0,240,255,0.2)] transition-all p-2"
                    >
                        <div className="w-12 h-12 bg-black border border-[#1A1D2E] overflow-hidden shrink-0">
                            {coverUrl(m) ? (
                                <img src={coverUrl(m)} alt={m.title} className="w-full h-full object-cover" />
                            ) : (
                                <div className="w-full h-full grid-bg flex items-center justify-center">
                                    <Disc3 className="w-5 h-5 text-zinc-700" />
                                </div>
                            )}
                        </div>
                        <div className="min-w-0 flex-1">
                            <div className="font-display font-bold text-xs text-white truncate group-hover:text-neon-cyan">
                                {m.title}
                            </div>
                            <div className="label truncate" style={{ fontSize: 9 }}>
                                {m.artist || "—"} · {fmtTime(m.duration || 0)}
                            </div>
                            <div className="flex items-center gap-1 mt-1 flex-wrap">
                                {m.bpm && (
                                    <span className="label px-1 border border-neon-green/40 text-neon-green" style={{ fontSize: 9 }}>
                                        {m.bpm}
                                    </span>
                                )}
                                {m.camelot && (
                                    <span className="label px-1 border border-neon-cyan/40 text-neon-cyan" style={{ fontSize: 9 }}>
                                        {m.camelot}
                                    </span>
                                )}
                                {(m.tags || []).slice(0, 2).map((t) => (
                                    <span
                                        key={t}
                                        className="label px-1 border border-neon-green/30 text-neon-green/80"
                                        style={{ fontSize: 9 }}
                                    >
                                        #{t}
                                    </span>
                                ))}
                            </div>
                        </div>
                    </Link>
                ))}
            </div>
        </div>
    );
};
