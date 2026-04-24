import { useEffect, useRef, useState } from "react";
import { usePlayer } from "../../contexts/PlayerContext";
import { VuMeter } from "../VuMeter";

// Visual-only EQ knob. Reacts to analyser band energy for a "breathing" feel.
const Knob = ({ value = 0, label, color = "#00F0FF", size = 52 }) => {
    const angle = -135 + Math.max(0, Math.min(1, value)) * 270; // -135..+135
    return (
        <div className="flex flex-col items-center gap-1.5 select-none">
            <div
                className="relative rounded-full"
                style={{
                    width: size,
                    height: size,
                    background: "radial-gradient(circle at 35% 30%, #2a2d3e, #0a0c14 75%)",
                    boxShadow:
                        "inset 0 0 8px rgba(0,0,0,0.8), 0 0 8px rgba(0,0,0,0.6), inset 0 0 0 1px rgba(255,255,255,0.04)",
                }}
            >
                {/* ring markers */}
                <div
                    className="absolute inset-0 rounded-full"
                    style={{
                        background: `conic-gradient(from 225deg, ${color}40 0deg, ${color}00 ${Math.max(0, angle + 135) * 1.1}deg, transparent ${Math.max(0, angle + 135) * 1.1}deg)`,
                        mask: "radial-gradient(circle, transparent 55%, #000 56%, #000 100%)",
                        WebkitMask: "radial-gradient(circle, transparent 55%, #000 56%, #000 100%)",
                    }}
                />
                {/* indicator */}
                <div
                    className="absolute left-1/2 top-1/2 origin-center"
                    style={{
                        width: 2,
                        height: size * 0.45,
                        background: color,
                        boxShadow: `0 0 6px ${color}`,
                        transform: `translate(-50%, -100%) rotate(${angle}deg)`,
                        transformOrigin: "50% 100%",
                    }}
                />
            </div>
            <div className="label tracking-[0.2em]" style={{ color: "#5C6170", fontSize: 9 }}>
                {label}
            </div>
        </div>
    );
};

export const MixerChannel = ({ label = "CH 1", color = "#00F0FF", active = true }) => {
    const { analyser, playing } = usePlayer();
    const [bands, setBands] = useState({ hi: 0.5, mid: 0.5, lo: 0.5 });
    const rafRef = useRef(null);

    useEffect(() => {
        if (!analyser) return;
        const buf = new Uint8Array(analyser.frequencyBinCount);
        const tick = () => {
            analyser.getByteFrequencyData(buf);
            const n = buf.length;
            const loAvg = avg(buf, 0, Math.floor(n * 0.1));
            const midAvg = avg(buf, Math.floor(n * 0.1), Math.floor(n * 0.5));
            const hiAvg = avg(buf, Math.floor(n * 0.5), n);
            setBands((b) => ({
                lo: 0.3 + loAvg * 0.7 * smoothing(b.lo, loAvg),
                mid: 0.3 + midAvg * 0.7 * smoothing(b.mid, midAvg),
                hi: 0.3 + hiAvg * 0.7 * smoothing(b.hi, hiAvg),
            }));
            rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
        return () => cancelAnimationFrame(rafRef.current);
    }, [analyser]);

    const faderHeight = playing ? 78 : 40; // "pushed up" when active

    return (
        <div
            data-testid={`mixer-channel-${label.replace(/\s+/g, "-").toLowerCase()}`}
            className="flex flex-col items-center gap-2 px-2 py-3 border border-[#1A1D2E] bg-[#0a0c14]"
            style={{ minWidth: 80 }}
        >
            <span className="label" style={{ color, fontSize: 10 }}>
                {label}
            </span>
            <Knob value={bands.hi} label="HI" color={color} />
            <Knob value={bands.mid} label="MID" color={color} />
            <Knob value={bands.lo} label="LOW" color={color} />
            {/* VU meter */}
            <div className="h-20 w-3 mt-1">
                <VuMeter orientation="vertical" label={label} />
            </div>
            {/* Channel fader */}
            <div className="relative mt-2 w-6 h-24 bg-black border border-[#1A1D2E]">
                <div
                    className="absolute left-1/2 -translate-x-1/2 w-5 rounded-sm transition-all duration-200"
                    style={{
                        bottom: faderHeight,
                        height: 8,
                        background: `linear-gradient(180deg, ${color}, #0a0c14)`,
                        boxShadow: `0 0 6px ${color}`,
                    }}
                />
                <div
                    className="absolute left-1/2 -translate-x-1/2 bottom-0 w-[2px]"
                    style={{ height: faderHeight + 4, background: `${color}30` }}
                />
            </div>
            {active ? (
                <span className="label px-1 py-0.5 border border-neon-cyan/40 text-neon-cyan" style={{ fontSize: 9 }}>
                    CUE
                </span>
            ) : (
                <span className="label text-zinc-600" style={{ fontSize: 9 }}>
                    OFF
                </span>
            )}
        </div>
    );
};

function avg(buf, a, b) {
    let s = 0;
    for (let i = a; i < b; i++) s += buf[i];
    return (b - a) > 0 ? s / (b - a) / 255 : 0;
}
function smoothing(prev, next) {
    return 0.3 + 0.7 * next;
}
