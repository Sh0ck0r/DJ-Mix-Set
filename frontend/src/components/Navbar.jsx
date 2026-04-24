import { Link, useLocation, useNavigate } from "react-router-dom";
import { Disc3, Search, Lock, LogOut } from "lucide-react";
import { useState, useEffect } from "react";

const NavLink = ({ to, label, active }) => (
    <Link
        to={to}
        data-testid={`nav-${label.toLowerCase()}`}
        className={`label transition-colors hover:text-neon-cyan ${active ? "text-neon-cyan glow-cyan" : "text-zinc-400"}`}
    >
        {label}
    </Link>
);

export const Navbar = ({ onSearch }) => {
    const loc = useLocation();
    const nav = useNavigate();
    const [q, setQ] = useState("");
    const [authed, setAuthed] = useState(!!localStorage.getItem("mixdeck_token"));

    useEffect(() => {
        const handler = () => setAuthed(!!localStorage.getItem("mixdeck_token"));
        window.addEventListener("storage", handler);
        return () => window.removeEventListener("storage", handler);
    }, []);

    const submit = (e) => {
        e.preventDefault();
        onSearch?.(q);
        if (loc.pathname !== "/") nav("/");
    };

    const logout = () => {
        localStorage.removeItem("mixdeck_token");
        setAuthed(false);
        nav("/");
    };

    return (
        <header
            data-testid="main-navbar"
            className="sticky top-0 z-40 backdrop-blur-xl bg-[#050505]/80 border-b border-neon-cyan/20"
        >
            <div className="max-w-[1600px] mx-auto px-4 md:px-8 h-16 flex items-center gap-4 md:gap-8">
                <Link to="/" data-testid="logo-link" className="flex items-center gap-2 group">
                    <Disc3 className="w-6 h-6 text-neon-cyan group-hover:animate-spin" strokeWidth={1.5} />
                    <span className="font-display font-black text-lg tracking-[0.2em] text-white">
                        MIX<span className="text-neon-cyan glow-cyan">DECK</span>
                    </span>
                </Link>

                <nav className="hidden md:flex items-center gap-6 ml-4">
                    <NavLink to="/" label="LIBRARY" active={loc.pathname === "/"} />
                    <NavLink to="/admin" label="ADMIN" active={loc.pathname.startsWith("/admin")} />
                </nav>

                <form onSubmit={submit} className="ml-auto flex-1 max-w-md hidden sm:block">
                    <div className="relative">
                        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
                        <input
                            data-testid="search-input"
                            value={q}
                            onChange={(e) => setQ(e.target.value)}
                            placeholder="SEARCH MIXES, ARTISTS, GENRES…"
                            className="w-full bg-[#0D0E15] border border-[#1A1D2E] focus:border-neon-cyan focus:outline-none pl-10 pr-3 py-2 text-xs tracking-widest uppercase font-mono text-white placeholder:text-zinc-600"
                        />
                    </div>
                </form>

                <div className="flex items-center gap-3 ml-auto sm:ml-0">
                    {authed ? (
                        <button
                            data-testid="logout-button"
                            onClick={logout}
                            className="label hover:text-neon-red flex items-center gap-1.5"
                            title="Logout admin"
                        >
                            <LogOut className="w-3.5 h-3.5" /> SIGN OUT
                        </button>
                    ) : (
                        <Link
                            to="/admin/login"
                            data-testid="admin-login-link"
                            className="label hover:text-neon-cyan flex items-center gap-1.5"
                        >
                            <Lock className="w-3.5 h-3.5" /> ADMIN
                        </Link>
                    )}
                </div>
            </div>
        </header>
    );
};
