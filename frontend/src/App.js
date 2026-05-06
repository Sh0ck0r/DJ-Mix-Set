import { useState } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { PlayerProvider } from "./contexts/PlayerContext";
import { Navbar } from "./components/Navbar";
import { MiniPlayer } from "./components/MiniPlayer";
import { Library } from "./pages/Library";
import { MixDetail } from "./pages/MixDetail";
import { AdminLogin } from "./pages/AdminLogin";
import { AdminDashboard } from "./pages/AdminDashboard";
import { AdminSettings } from "./pages/AdminSettings";

function App() {
    const [search, setSearch] = useState("");
    return (
        <div className="App min-h-screen text-white">
            <BrowserRouter>
                <PlayerProvider>
                    <Navbar onSearch={setSearch} />
                    <main>
                        <Routes>
                            <Route path="/" element={<Library search={search} />} />
                            <Route path="/mix/:id" element={<MixDetail />} />
                            <Route path="/admin/login" element={<AdminLogin />} />
                            <Route path="/admin" element={<AdminDashboard />} />
                            <Route path="/admin/settings" element={<AdminSettings />} />
                        </Routes>
                    </main>
                    <MiniPlayer />
                    <Toaster
                        theme="dark"
                        position="top-right"
                        toastOptions={{
                            classNames: {
                                toast: "!bg-[#0D0E15] !border !border-neon-cyan/30 !text-white !rounded-none !font-mono !text-xs !tracking-widest",
                            },
                        }}
                    />
                </PlayerProvider>
            </BrowserRouter>
        </div>
    );
}

export default App;
