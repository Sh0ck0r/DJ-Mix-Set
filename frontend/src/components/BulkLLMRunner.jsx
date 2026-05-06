import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Loader2, Sparkles, FileText, Tag, CheckCircle2, AlertTriangle, X } from "lucide-react";

const KIND_META = {
    tags: {
        label: "AUTO-TAG ALL",
        verb: "tagging",
        Icon: Tag,
        description: "Generate mood/vibe tags for every mix that doesn't have any.",
    },
    descriptions: {
        label: "AUTO-METADATA ALL",
        verb: "describing",
        Icon: FileText,
        description: "Write a 2-4 sentence description for every mix that doesn't have one.",
    },
};

/**
 * Polls a bulk-LLM task and renders a live progress bar + counters.
 * Self-clears 5s after the task reaches a terminal state.
 */
export const BulkLLMRunner = ({ kind, onChanged }) => {
    const meta = KIND_META[kind];
    const [busy, setBusy] = useState(false);
    const [task, setTask] = useState(null);
    const [force, setForce] = useState(false);
    const pollRef = useRef(null);

    useEffect(() => () => clearInterval(pollRef.current), []);

    const start = async () => {
        if (busy) return;
        setBusy(true);
        try {
            const fn = kind === "tags" ? api.autoTagAll : api.autoDescribeAll;
            const res = await fn(force);
            const t = await api.bulkLLMStatus(res.task_id);
            setTask(t);
            startPolling(res.task_id);
            toast.success(`${meta.label} STARTED`, {
                description: `Processing ${t.total || "all eligible"} mix${t.total === 1 ? "" : "es"}…`,
            });
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed to start bulk task");
        } finally {
            setBusy(false);
        }
    };

    const startPolling = (taskId) => {
        clearInterval(pollRef.current);
        pollRef.current = setInterval(async () => {
            try {
                const t = await api.bulkLLMStatus(taskId);
                setTask(t);
                if (t.status !== "running") {
                    clearInterval(pollRef.current);
                    pollRef.current = null;
                    if (t.status === "done") {
                        toast.success(`${meta.label} COMPLETE`, {
                            description: `${t.succeeded || 0} succeeded · ${t.failed || 0} failed · ${t.skipped_existing || 0} already had ${kind === "tags" ? "tags" : "descriptions"}.`,
                        });
                        // Auto-clear success panel after 8s
                        setTimeout(() => setTask(null), 8000);
                    } else {
                        toast.error(`${meta.label} FAILED`, {
                            description: t.error || `${t.succeeded || 0} succeeded before failure`,
                        });
                        // Keep failed panel sticky until user dismisses (so they can read errors)
                    }
                    onChanged?.();
                }
            } catch {
                clearInterval(pollRef.current);
                pollRef.current = null;
            }
        }, 1500);
    };

    const dismiss = () => {
        clearInterval(pollRef.current);
        pollRef.current = null;
        setTask(null);
    };

    const Icon = meta.Icon;
    const running = task?.status === "running";
    const pct = task?.total ? Math.round((task.processed / task.total) * 100) : 0;

    return (
        <div
            className="border border-[#1A1D2E] bg-black/30 p-4"
            data-testid={`bulk-runner-${kind}`}
        >
            <div className="flex items-start gap-3">
                <Icon className="w-4 h-4 text-neon-green mt-1 shrink-0" />
                <div className="flex-1 min-w-0">
                    <div className="font-display font-bold text-sm tracking-widest uppercase text-white">
                        {meta.label}
                    </div>
                    <div className="font-mono text-[11px] text-zinc-500 mt-0.5">
                        {meta.description}
                    </div>
                </div>
                <label className="flex items-center gap-1.5 cursor-pointer select-none mr-3" title="Re-run on mixes that already have results">
                    <input
                        type="checkbox"
                        checked={force}
                        onChange={(e) => setForce(e.target.checked)}
                        data-testid={`bulk-force-${kind}`}
                        className="w-3.5 h-3.5 accent-neon-cyan"
                    />
                    <span className="label text-zinc-500">FORCE</span>
                </label>
                <button
                    onClick={start}
                    disabled={busy || running}
                    data-testid={`bulk-start-${kind}`}
                    className="bg-neon-green text-black font-display font-black tracking-widest uppercase px-3 py-1.5 hover:bg-white transition-colors disabled:opacity-30 flex items-center gap-1.5 shadow-[0_0_15px_rgba(57,255,20,0.25)]"
                >
                    {busy || running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
                    {running ? `${meta.verb.toUpperCase()}…` : busy ? "STARTING…" : "RUN"}
                </button>
            </div>

            {task && (
                <div className="mt-3" data-testid={`bulk-progress-${kind}`}>
                    {/* Progress bar */}
                    <div className="h-1.5 bg-black border border-[#1A1D2E] overflow-hidden">
                        <div
                            className={`h-full transition-all duration-500 ${
                                task.status === "failed" ? "bg-neon-red" : "bg-neon-green"
                            }`}
                            style={{
                                width: `${pct}%`,
                                boxShadow: task.status === "failed"
                                    ? "0 0 12px rgba(255,0,60,0.5)"
                                    : "0 0 12px rgba(57,255,20,0.5)",
                            }}
                        />
                    </div>
                    <div className="flex items-center justify-between mt-2 gap-3 flex-wrap">
                        <div className="flex items-center gap-3 font-mono text-xs flex-wrap">
                            <span className="text-zinc-400">
                                <span className="text-neon-cyan">{task.processed}</span>/{task.total}
                            </span>
                            <span className="text-neon-green flex items-center gap-1">
                                <CheckCircle2 className="w-3 h-3" /> {task.succeeded || 0}
                            </span>
                            {task.failed > 0 && (
                                <span className="text-neon-red flex items-center gap-1">
                                    <AlertTriangle className="w-3 h-3" /> {task.failed}
                                </span>
                            )}
                            {task.skipped_existing > 0 && (
                                <span className="text-zinc-500">{task.skipped_existing} already had</span>
                            )}
                            {task.status === "done" && <span className="label text-neon-green">DONE</span>}
                            {task.status === "failed" && <span className="label text-neon-red">FAILED</span>}
                        </div>
                        {!running && (
                            <button
                                onClick={dismiss}
                                className="text-zinc-500 hover:text-neon-red"
                                aria-label="Dismiss"
                            >
                                <X className="w-3.5 h-3.5" />
                            </button>
                        )}
                    </div>
                    {running && task.current_mix && (
                        <div className="font-mono text-[11px] text-zinc-500 mt-1 truncate">
                            {meta.verb}: <span className="text-neon-cyan">{task.current_mix.title}</span>
                        </div>
                    )}
                    {task.error && (
                        <div className="font-mono text-[11px] text-neon-red mt-1 break-words">
                            {task.error}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};
