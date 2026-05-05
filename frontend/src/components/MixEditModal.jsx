import { useState, useEffect } from "react";
import { api } from "../lib/api";
import { toast } from "sonner";
import { X, Save, Loader2, Edit3 } from "lucide-react";

const Field = ({ label, ...props }) => (
    <label className="block">
        <span className="label block mb-1.5">{label}</span>
        <input
            {...props}
            className="w-full bg-black border border-[#1A1D2E] focus:border-neon-cyan focus:outline-none px-3 py-2 text-white font-mono text-sm"
        />
    </label>
);

export const MixEditModal = ({ mix, open, onClose, onSaved }) => {
    const [form, setForm] = useState({
        title: "", artist: "", genre: "", bpm: "", key: "", camelot: "", description: "",
    });
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (mix) {
            setForm({
                title: mix.title || "",
                artist: mix.artist || "",
                genre: mix.genre || "",
                bpm: mix.bpm ? String(mix.bpm) : "",
                key: mix.key || "",
                camelot: mix.camelot || "",
                description: mix.description || "",
            });
        }
    }, [mix]);

    if (!open || !mix) return null;

    const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

    const save = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            const body = {
                title: form.title.trim() || undefined,
                artist: form.artist.trim() || null,
                genre: form.genre.trim() || null,
                bpm: form.bpm ? parseInt(form.bpm, 10) : null,
                key: form.key.trim() || null,
                camelot: form.camelot.trim().toUpperCase() || null,
                description: form.description || null,
            };
            // Strip undefined; PATCH treats null as explicit clear -> we send null fine
            const cleaned = Object.fromEntries(Object.entries(body).filter(([_, v]) => v !== undefined));
            await api.updateMix(mix.id, cleaned);
            toast.success("METADATA UPDATED");
            onSaved?.();
            onClose?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Update failed");
        } finally {
            setSaving(false);
        }
    };

    return (
        <div
            data-testid="mix-edit-modal"
            className="fixed inset-0 z-[60] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={onClose}
        >
            <form
                onClick={(e) => e.stopPropagation()}
                onSubmit={save}
                className="w-full max-w-xl border border-neon-cyan/40 bg-[#0a0c14] scanlines relative shadow-[0_0_60px_rgba(0,240,255,0.2)]"
            >
                <div className="flex items-center justify-between px-5 py-3 border-b border-[#1A1D2E]">
                    <div className="flex items-center gap-2">
                        <Edit3 className="w-4 h-4 text-neon-cyan" />
                        <span className="font-display font-bold tracking-widest uppercase text-sm">
                            EDIT MIX <span className="text-neon-cyan">METADATA</span>
                        </span>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        data-testid="close-edit-modal"
                        className="text-zinc-500 hover:text-neon-red transition-colors"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
                <div className="p-5 space-y-4">
                    <Field label="TITLE" value={form.title} onChange={set("title")} data-testid="edit-title" />
                    <div className="grid grid-cols-2 gap-3">
                        <Field label="DJ / ARTIST" value={form.artist} onChange={set("artist")} data-testid="edit-artist" />
                        <Field label="GENRE" value={form.genre} onChange={set("genre")} data-testid="edit-genre" />
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <Field label="BPM" type="number" value={form.bpm} onChange={set("bpm")} data-testid="edit-bpm" />
                        <Field label="KEY" placeholder="A minor" value={form.key} onChange={set("key")} data-testid="edit-key" />
                        <Field label="CAMELOT" placeholder="8A" value={form.camelot} onChange={set("camelot")} data-testid="edit-camelot" />
                    </div>
                    <label className="block">
                        <span className="label block mb-1.5">DESCRIPTION</span>
                        <textarea
                            value={form.description}
                            onChange={set("description")}
                            rows={3}
                            data-testid="edit-description"
                            className="w-full bg-black border border-[#1A1D2E] focus:border-neon-cyan focus:outline-none px-3 py-2 text-white font-mono text-sm"
                        />
                    </label>
                </div>
                <div className="px-5 pb-5">
                    <button
                        type="submit"
                        disabled={saving}
                        data-testid="save-mix-edit"
                        className="w-full bg-neon-cyan text-black font-display font-black tracking-widest uppercase py-2.5 hover:bg-white transition-colors disabled:opacity-30 flex items-center justify-center gap-2"
                    >
                        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                        {saving ? "SAVING…" : "SAVE METADATA"}
                    </button>
                </div>
            </form>
        </div>
    );
};
