import { useEffect, useRef } from "react";
import { coverUrl } from "../../lib/api";

export const JogWheel = ({
    mix,
    playing = false,
    currentTime = 0,
    duration = 0,
    bpm = null,
    label = "A",
    side = "left",
    size = 260,
    art = null,
    active = true,
}) => {
    const rotRef = useRef(0);
    const rafRef = useRef(null);
    const diskRef = useRef(null);
    const cover = art || coverUrl(mix);

    // Smooth rotation independent of audio time — 33rpm-ish feel
    useEffect(() => {
        let last = performance.now();
        const loop = (t) => {
            const dt = (t - last) / 1000;
            last = t;
            if (playing && active) rotRef.current = (rotRef.current + dt * 45) % 360;
            if (diskRef.current) {
                diskRef.current.style.transform = `rotate(${rotRef.current}deg)`;
            }
            rafRef.current = requestAnimationFrame(loop);
        };
        rafRef.current = requestAnimationFrame(loop);
        return () => cancelAnimationFrame(rafRef.current);
    }, [playing, active]);

    const progress = duration > 0 ? Math.min(1, currentTime / duration) : 0;
    const ring = size * 0.47;
    const circ = 2 * Math.PI * ring;
    const dash = circ * progress;

    return (
        <div
            data-testid={`jog-wheel-${label}`}
            className="relative select-none"
            style={{ width: size, height: size }}
        >
            {/* Outer bezel */}
            <div
                className="absolute inset-0 rounded-full"
                style={{
                    background:
                        "radial-gradient(circle at 30% 30%, #2a2d3e 0%, #0e1018 55%, #05060a 100%)",
                    boxShadow:
                        "inset 0 0 20px rgba(0,0,0,0.85), 0 0 40px rgba(0,240,255,0.08), 0 8px 30px rgba(0,0,0,0.7)",
                }}
            />
            {/* Progress ring */}
            <svg className="absolute inset-0" viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
                <circle cx={size / 2} cy={size / 2} r={ring} fill="none" stroke="#161824" strokeWidth="3" />
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={ring}
                    fill="none"
                    stroke={active ? "#00F0FF" : "#39FF14"}
                    strokeWidth="3"
                    strokeDasharray={`${dash} ${circ - dash}`}
                    style={{
                        filter: active ? "drop-shadow(0 0 6px #00F0FF)" : "drop-shadow(0 0 6px #39FF14)",
                        transition: "stroke-dasharray 0.1s linear",
                    }}
                />
            </svg>
            {/* Tick marks around edge */}
            <div className="absolute inset-0 pointer-events-none">
                {Array.from({ length: 60 }).map((_, i) => {
                    const angle = (i / 60) * 360;
                    const major = i % 5 === 0;
                    return (
                        <div
                            key={i}
                            className="absolute left-1/2 top-1/2 origin-bottom"
                            style={{
                                width: 1,
                                height: major ? 8 : 4,
                                background: major ? "#5C6170" : "#2a2d3e",
                                transform: `translate(-50%, -${size / 2 - 8}px) rotate(${angle}deg)`,
                                transformOrigin: `50% ${size / 2 - 8}px`,
                            }}
                        />
                    );
                })}
            </div>
            {/* Jog disc */}
            <div
                ref={diskRef}
                className="absolute rounded-full overflow-hidden"
                style={{
                    top: "14%",
                    left: "14%",
                    right: "14%",
                    bottom: "14%",
                    background: "radial-gradient(circle at 40% 40%, #1a1d2e, #05060a 80%)",
                    boxShadow:
                        "inset 0 0 30px rgba(0,0,0,0.9), 0 0 10px rgba(0,240,255,0.15)",
                }}
            >
                {cover ? (
                    <img
                        src={cover}
                        alt=""
                        className="w-full h-full object-cover opacity-85"
                        style={{ mixBlendMode: "normal" }}
                    />
                ) : (
                    <div className="w-full h-full grid-bg" />
                )}
                {/* Radial grooves overlay */}
                <div
                    className="absolute inset-0"
                    style={{
                        background:
                            "repeating-radial-gradient(circle at center, rgba(0,0,0,0.4) 0 1px, transparent 1px 3px)",
                        mixBlendMode: "multiply",
                    }}
                />
                {/* Center hub */}
                <div
                    className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full flex flex-col items-center justify-center"
                    style={{
                        width: size * 0.3,
                        height: size * 0.3,
                        background:
                            "radial-gradient(circle, #111425 0%, #000 100%)",
                        border: `1px solid ${active ? "#00F0FF" : "#39FF14"}`,
                        boxShadow: `0 0 14px ${active ? "rgba(0,240,255,0.4)" : "rgba(57,255,20,0.3)"}`,
                    }}
                >
                    <div
                        className="label tracking-[0.25em]"
                        style={{ color: active ? "#00F0FF" : "#39FF14", fontSize: size * 0.055 }}
                    >
                        DECK {label}
                    </div>
                    {bpm ? (
                        <div
                            className="font-display font-black leading-none mt-0.5"
                            style={{ color: "#fff", fontSize: size * 0.09 }}
                        >
                            {bpm}
                        </div>
                    ) : (
                        <div className="label text-zinc-600" style={{ fontSize: size * 0.045 }}>
                            — BPM
                        </div>
                    )}
                    <div className="label text-zinc-500" style={{ fontSize: size * 0.035 }}>
                        {active && playing ? "PLAYING" : active ? "PAUSED" : "CUED"}
                    </div>
                </div>
            </div>
            {/* REC LED when active + playing */}
            <div
                className="absolute rounded-full"
                style={{
                    top: side === "left" ? 18 : 18,
                    right: side === "left" ? 18 : "auto",
                    left: side === "left" ? "auto" : 18,
                    width: 8,
                    height: 8,
                    background: active && playing ? "#FF003C" : "#1a1d2e",
                    boxShadow: active && playing ? "0 0 10px #FF003C" : "none",
                }}
            />
        </div>
    );
};
