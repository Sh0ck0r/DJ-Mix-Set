import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Activity, CheckCircle2, Loader2, AlertTriangle, Layers, Zap } from "lucide-react";

/**
 * Live BPM/Key analysis overview strip for the admin dashboard.
 * Polls /api/admin/analysis_overview every 4s while any work is pending/running.
 * "ANALYZE ALL" queues every un-done mix.
 */
export const AnalysisOverviewBar = ({ onChanged }) => {
    const [data, setData] = useState(null);
    const [busy, setBusy] = useState(false);

    const load = useCallback(async () => {
        try {
            setData(await api.analysisOverview());
        } catch {
            // silent: endpoint requires admin token; if it fails the row just hides
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    // Auto-poll while there is active work
    useEffect(() => {
        if (!data) return;
        const c = data.counts || {};
        const active = (c.pending || 0) + (c.running || 0);
        if (active === 0) return;
        const iv = setInterval(load, 4000);
        return () => clearInterval(iv);
    }, [data, load]);

    const analyzeAll = async () => {
        if (busy) return;
        setBusy(true);
        try {
            const res = await api.analyzeAll(false);
            toast.success(`QUEUED ${res.queued ?? 0} FOR ANALYSIS`, {
                description: res.skipped ? `${res.skipped} already done · refresh later for results.` : undefined,
            });
            await load();
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed to queue analysis");
        } finally {
            setBusy(false);
        }
    };

    if (!data) return null;
    const { counts = {}, total = 0, active_workers = 0 } = data;
    const done = counts.done || 0;
    const pending = counts.pending || 0;
    const running = counts.running || 0;
    const failed = counts.failed || 0;
    const none = counts.none || 0;
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    const queueable = none + failed + pending + running; // anything not done
    const allDone = total > 0 && done === total;

    return (
        <div
            className="border border-[#1A1D2E] bg-[#0a0c14] mb-6 scanlines relative"
            data-testid="analysis-overview-bar"
        >
            <div className="flex items-stretch flex-wrap">
                <Cell icon={<Layers />} label="LIBRARY" value={total} tone="cyan" testid="overview-total" />
                <Cell
                    icon={<CheckCircle2 />}
                    label="ANALYZED"
                    value={`${done} · ${pct}%`}
                    tone="green"
                    testid="overview-done"
                />
                <Cell
                    icon={running > 0 ? <Activity className="animate-pulse" /> : <Activity />}
                    label="RUNNING"
                    value={running}
                    tone={running > 0 ? "cyan" : "muted"}
                    testid="overview-running"
                />
                <Cell
                    icon={pending > 0 ? <Loader2 className="animate-spin" /> : <Loader2 />}
                    label="QUEUED"
                    value={pending}
                    tone={pending > 0 ? "cyan" : "muted"}
                    testid="overview-pending"
                />
                <Cell
                    icon={<AlertTriangle />}
                    label="FAILED"
                    value={failed}
                    tone={failed > 0 ? "red" : "muted"}
                    testid="overview-failed"
                />
                <Cell
                    icon={<Activity />}
                    label="WORKERS"
                    value={active_workers}
                    tone={active_workers > 0 ? "green" : "muted"}
                    testid="overview-workers"
                />
                <div className="ml-auto flex items-center px-4 border-l border-[#1A1D2E]">
                    <button
                        onClick={analyzeAll}
                        disabled={busy || queueable === 0 || allDone}
                        data-testid="analyze-all-button"
                        title={allDone ? "Everything is analyzed" : `Queue analysis for ${queueable} mix(es)`}
                        className="bg-neon-green text-black font-display font-black tracking-widest uppercase px-4 py-2 hover:bg-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-2 shadow-[0_0_18px_rgba(57,255,20,0.25)]"
                    >
                        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                        {allDone ? "ALL ANALYZED" : busy ? "QUEUING…" : "ANALYZE ALL"}
                    </button>
                </div>
            </div>
            {/* progress bar across the bottom */}
            <div className="h-1 bg-black border-t border-[#1A1D2E] overflow-hidden">
                <div
                    className="h-full bg-neon-green transition-all duration-500"
                    style={{
                        width: `${pct}%`,
                        boxShadow: "0 0 12px rgba(57,255,20,0.5)",
                    }}
                    data-testid="overview-progress-bar"
                />
            </div>
        </div>
    );
};

const Cell = ({ icon, label, value, tone, testid }) => {
    const tones = {
        cyan: "text-neon-cyan",
        green: "text-neon-green",
        red: "text-neon-red",
        muted: "text-zinc-500",
    };
    return (
        <div
            className="flex items-center gap-3 px-4 py-3 border-r border-[#1A1D2E] min-w-[140px]"
            data-testid={testid}
        >
            <span className={`[&_svg]:w-4 [&_svg]:h-4 ${tones[tone]}`}>{icon}</span>
            <div>
                <div className="label text-zinc-500">{label}</div>
                <div className={`font-display font-black text-xl leading-none mt-0.5 ${tones[tone]}`}>{value}</div>
            </div>
        </div>
    );
};
