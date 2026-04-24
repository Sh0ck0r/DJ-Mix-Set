import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Lock, Loader2 } from "lucide-react";
import { toast } from "sonner";

export const AdminLogin = () => {
    const [password, setPassword] = useState("");
    const [loading, setLoading] = useState(false);
    const nav = useNavigate();

    const submit = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            const { token } = await api.login(password);
            localStorage.setItem("mixdeck_token", token);
            window.dispatchEvent(new Event("storage"));
            toast.success("ACCESS GRANTED");
            nav("/admin");
        } catch (err) {
            toast.error("INVALID PASSWORD");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-[80vh] flex items-center justify-center px-4">
            <form
                onSubmit={submit}
                data-testid="admin-login-form"
                className="w-full max-w-sm border border-[#1A1D2E] bg-[#0a0c14] p-8 relative scanlines"
            >
                <div className="absolute -top-px left-0 right-0 h-px bg-gradient-to-r from-transparent via-neon-cyan to-transparent" />
                <div className="flex flex-col items-center mb-6">
                    <div className="w-12 h-12 border border-neon-cyan rounded-full flex items-center justify-center mb-3 shadow-[0_0_20px_rgba(0,240,255,0.4)]">
                        <Lock className="w-5 h-5 text-neon-cyan" />
                    </div>
                    <h1 className="font-display font-black text-xl uppercase tracking-widest">
                        ADMIN <span className="text-neon-cyan">ACCESS</span>
                    </h1>
                    <p className="label mt-2">// AUTHORIZED PERSONNEL ONLY</p>
                </div>
                <label className="label mb-2 block">PASSWORD</label>
                <input
                    type="password"
                    autoFocus
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    data-testid="admin-password-input"
                    className="w-full bg-black border border-[#1A1D2E] focus:border-neon-cyan focus:outline-none px-3 py-2.5 text-white font-mono"
                    placeholder="••••••••"
                />
                <button
                    type="submit"
                    disabled={loading || !password}
                    data-testid="admin-login-submit"
                    className="w-full mt-6 bg-neon-cyan text-black font-display font-black tracking-widest uppercase py-3 hover:bg-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center gap-2 shadow-[0_0_20px_rgba(0,240,255,0.4)]"
                >
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "ENTER DECK"}
                </button>
            </form>
        </div>
    );
};
