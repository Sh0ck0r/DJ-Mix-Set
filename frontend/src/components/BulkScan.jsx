import { useState } from "react";
import { api } from "../lib/api";
import { toast } from "sonner";
import { FolderSearch, Loader2, CheckCircle2, AlertTriangle, FileAudio, FileText, Image as ImageIcon, Radar } from "lucide-react";

export const BulkScan = ({ onScanned }) => {
    const [path, setPath] = useState(localStorage.getItem("mixdeck_scan_path") || "");
    const [recursive, setRecursive] = useState(true);
    const [genre, setGenre] = useState("");
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);

    const run = async (e) => {
        e.preventDefault();
        if (!path.trim()) {
            toast.error("Enter a directory path");
            return;
        }
        localStorage.setItem("mixdeck_scan_path", path);
        setBusy(true);
        setResult(null);
        try {
            const data = await api.scanDirectory(path.trim(), recursive, genre.trim());
            setResult(data);
            if (data.added_count > 0) {
                toast.success(`IMPORTED ${data.added_count} MIX${data.added_count === 1 ? "" : "ES"}`);
                onScanned?.();
            } else if (data.skipped_count > 0 && data.failed_count === 0) {
                toast.success(`ALL ${data.skipped_count} ALREADY INDEXED`);
            } else if (data.scanned === 0) {
                toast.error("No audio files found");
            }
        } catch (err) {
            toast.error(err.response?.data?.detail || "Scan failed");
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="border border-[#1A1D2E] bg-[#0a0c14] p-5 md:p-6 scanlines relative" data-testid="bulk-scan-panel">
            <div className="flex items-center gap-2 mb-4">
                <Radar className="w-4 h-4 text-neon-cyan animate-pulse" />
                <span className="label text-neon-cyan">// BULK DIRECTORY SCAN</span>
            </div>
            <p className="font-mono text-xs text-zinc-500 leading-relaxed mb-4">
                Point at any folder on the server. Every <span className="text-neon-cyan">.mp3 / .flac / .wav / .m4a / .ogg</span>{" "}
                with a matching <span className="text-neon-green">.cue</span> is imported and referenced in place — no disk duplication.
                Cover art auto-detected from <span className="text-neon-cyan">cover.jpg / folder.jpg / {'{stem}'}.jpg</span>.
                Re-running skips already-indexed files.
            </p>

            <form onSubmit={run} className="space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-[1fr_180px] gap-3">
                    <label className="block">
                        <span className="label block mb-1.5">ABSOLUTE PATH ON SERVER</span>
                        <div className="relative">
                            <FolderSearch className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-neon-cyan" />
                            <input
                                data-testid="scan-path-input"
                                value={path}
                                onChange={(e) => setPath(e.target.value)}
                                placeholder="/mnt/dj-mixes"
                                className="w-full bg-black border border-[#1A1D2E] focus:border-neon-cyan focus:outline-none pl-9 pr-3 py-2.5 text-white font-mono text-sm"
                            />
                        </div>
                    </label>
                    <label className="block">
                        <span className="label block mb-1.5">DEFAULT GENRE (OPT)</span>
                        <input
                            data-testid="scan-genre-input"
                            value={genre}
                            onChange={(e) => setGenre(e.target.value)}
                            placeholder="Trance"
                            className="w-full bg-black border border-[#1A1D2E] focus:border-neon-cyan focus:outline-none px-3 py-2.5 text-white font-mono text-sm"
                        />
                    </label>
                </div>
                <div className="flex items-center gap-4 flex-wrap">
                    <label className="flex items-center gap-2 cursor-pointer select-none">
                        <input
                            type="checkbox"
                            checked={recursive}
                            onChange={(e) => setRecursive(e.target.checked)}
                            data-testid="scan-recursive-toggle"
                            className="w-4 h-4 accent-neon-cyan"
                        />
                        <span className="label">RECURSIVE (INCLUDE SUBFOLDERS)</span>
                    </label>
                    <button
                        type="submit"
                        disabled={busy}
                        data-testid="scan-submit-button"
                        className="ml-auto bg-neon-cyan text-black font-display font-black tracking-widest uppercase px-5 py-2.5 hover:bg-white transition-colors disabled:opacity-30 flex items-center gap-2 shadow-[0_0_20px_rgba(0,240,255,0.3)]"
                    >
                        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Radar className="w-4 h-4" />}
                        {busy ? "SCANNING…" : "SCAN NOW"}
                    </button>
                </div>
            </form>

            {result && (
                <ScanResult result={result} />
            )}
        </div>
    );
};

const ScanResult = ({ result }) => (
    <div className="mt-5 border border-[#1A1D2E]" data-testid="scan-result">
        <div className="grid grid-cols-4 text-center border-b border-[#1A1D2E]">
            <Stat label="SCANNED" value={result.scanned} color="cyan" />
            <Stat label="ADDED" value={result.added_count} color="green" />
            <Stat label="SKIPPED" value={result.skipped_count} color="muted" />
            <Stat label="FAILED" value={result.failed_count} color={result.failed_count ? "red" : "muted"} />
        </div>
        {result.added?.length > 0 && (
            <ResultSection title="IMPORTED" tone="green" items={result.added.map((a) => (
                <div key={a.id} className="px-3 py-2 grid grid-cols-[1fr_auto] gap-3 items-center border-b border-[#1A1D2E] last:border-b-0">
                    <div className="min-w-0">
                        <div className="font-display font-bold text-sm truncate text-white flex items-center gap-2">
                            <CheckCircle2 className="w-3.5 h-3.5 text-neon-green shrink-0" />
                            {a.title}
                        </div>
                        <div className="label truncate mt-0.5">{a.path}</div>
                    </div>
                    <div className="flex items-center gap-2">
                        <Badge icon={<FileText />} on={a.cue} label={`${a.tracks} TRX`} />
                        <Badge icon={<ImageIcon />} on={a.cover} label="ART" />
                        <Badge icon={<FileAudio />} on label="AUDIO" />
                    </div>
                </div>
            ))} />
        )}
        {result.skipped?.length > 0 && (
            <ResultSection title="SKIPPED" tone="muted" items={result.skipped.map((s, i) => (
                <div key={i} className="px-3 py-1.5 border-b border-[#1A1D2E] last:border-b-0">
                    <div className="label truncate">
                        <span className="text-zinc-600 mr-2">[{s.reason}]</span>
                        {s.path}
                    </div>
                </div>
            ))} />
        )}
        {result.failed?.length > 0 && (
            <ResultSection title="FAILED" tone="red" items={result.failed.map((f, i) => (
                <div key={i} className="px-3 py-2 border-b border-[#1A1D2E] last:border-b-0">
                    <div className="font-mono text-xs text-neon-red flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        {f.path}
                    </div>
                    <div className="label text-zinc-500 mt-0.5">{f.error}</div>
                </div>
            ))} />
        )}
    </div>
);

const Stat = ({ label, value, color }) => {
    const colors = {
        cyan: "text-neon-cyan",
        green: "text-neon-green",
        red: "text-neon-red",
        muted: "text-zinc-400",
    };
    return (
        <div className="p-3">
            <div className="label">{label}</div>
            <div className={`font-display font-black text-2xl ${colors[color]}`}>{value}</div>
        </div>
    );
};

const ResultSection = ({ title, items, tone = "muted" }) => {
    const tones = {
        green: "text-neon-green border-neon-green/30 bg-neon-green/5",
        muted: "text-zinc-400 border-[#1A1D2E] bg-black/20",
        red: "text-neon-red border-neon-red/30 bg-neon-red/5",
    };
    return (
        <div>
            <div className={`px-3 py-1.5 border-t border-b label ${tones[tone]}`}>
                {title} · {items.length}
            </div>
            <div className="max-h-60 overflow-auto">{items}</div>
        </div>
    );
};

const Badge = ({ icon, on, label }) => (
    <span
        className={`label px-2 py-1 border flex items-center gap-1 ${
            on ? "border-neon-cyan/40 text-neon-cyan" : "border-[#1A1D2E] text-zinc-600"
        }`}
    >
        <span className="[&_svg]:w-3 [&_svg]:h-3">{icon}</span> {label}
    </span>
);
