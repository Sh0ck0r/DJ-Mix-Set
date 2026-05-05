import { useEffect, useState } from "react";

export const Crossfader = ({ activeSide = "A" }) => {
    // Drift toward the active deck. Subtle sine wobble adds life.
    const target = activeSide === "A" ? -0.7 : 0.7;
    const [pos, setPos] = useState(target);
    useEffect(() => {
        const t = setInterval(() => {
            setPos((p) => {
                const wobble = Math.sin(Date.now() / 1500) * 0.04;
                // ease toward target
                return p + (target + wobble - p) * 0.08;
            });
        }, 60);
        return () => clearInterval(t);
    }, [target]);

    const x = 50 + pos * 50; // 0..100

    return (
        <div className="w-full" data-testid="crossfader">
            <div className="flex justify-between mb-1.5">
                <span className="label text-neon-cyan" style={{ fontSize: 10 }}>A</span>
                <span className="label" style={{ fontSize: 9 }}>CROSSFADER</span>
                <span className="label text-neon-green" style={{ fontSize: 10 }}>B</span>
            </div>
            <div className="relative h-6 bg-black border border-[#1A1D2E] overflow-hidden">
                {/* gradient background */}
                <div
                    className="absolute inset-0"
                    style={{
                        background:
                            "linear-gradient(to right, rgba(0,240,255,0.12), transparent 50%, rgba(57,255,20,0.12))",
                    }}
                />
                {/* tick marks */}
                <div className="absolute inset-0 flex items-center justify-between px-1">
                    {Array.from({ length: 13 }).map((_, i) => (
                        <div
                            key={i}
                            className="w-px"
                            style={{ height: i === 6 ? 10 : 6, background: i === 6 ? "#00F0FF" : "#2a2d3e" }}
                        />
                    ))}
                </div>
                {/* fader cap */}
                <div
                    className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-5 h-8 transition-all duration-75"
                    style={{
                        left: `${x}%`,
                        background:
                            "linear-gradient(180deg, #2a2d3e, #0a0c14)",
                        border: "1px solid #00F0FF",
                        boxShadow: "0 0 12px rgba(0,240,255,0.45)",
                    }}
                />
            </div>
        </div>
    );
};
