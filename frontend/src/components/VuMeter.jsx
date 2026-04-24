import { useEffect, useRef, useState } from "react";
import { usePlayer } from "../contexts/PlayerContext";

const SEGMENTS = 22;

export const VuMeter = ({ orientation = "vertical", label }) => {
    const { analyser, playing } = usePlayer();
    const [level, setLevel] = useState(0);
    const dataRef = useRef(null);
    const rafRef = useRef(null);
    const fakeRef = useRef(0);

    useEffect(() => {
        const tick = () => {
            if (analyser) {
                if (!dataRef.current || dataRef.current.length !== analyser.frequencyBinCount) {
                    dataRef.current = new Uint8Array(analyser.frequencyBinCount);
                }
                analyser.getByteFrequencyData(dataRef.current);
                let sum = 0;
                for (let i = 0; i < dataRef.current.length; i++) sum += dataRef.current[i];
                const avg = sum / dataRef.current.length / 255;
                setLevel((prev) => prev * 0.55 + avg * 0.45);
            } else if (playing) {
                // simulated meter when analyser unavailable (e.g. cross-origin audio)
                fakeRef.current += 0.06;
                const v = 0.45 + 0.4 * Math.abs(Math.sin(fakeRef.current)) + 0.15 * Math.random();
                setLevel(Math.min(1, v));
            } else {
                setLevel((prev) => prev * 0.85);
            }
            rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
        return () => cancelAnimationFrame(rafRef.current);
    }, [analyser, playing]);

    const litCount = Math.round(level * SEGMENTS);

    const segments = Array.from({ length: SEGMENTS }, (_, i) => {
        const fromTop = SEGMENTS - 1 - i;
        const lit = orientation === "vertical" ? fromTop < litCount : i < litCount;
        const ratio = (orientation === "vertical" ? fromTop : i) / SEGMENTS;
        let color = "#39FF14";
        if (ratio > 0.85) color = "#FF003C";
        else if (ratio > 0.65) color = "#F2E900";
        return { lit, color };
    });

    const isVertical = orientation === "vertical";
    return (
        <div
            data-testid={`vu-meter-${label || "meter"}`}
            className={`flex ${isVertical ? "flex-col-reverse" : "flex-row"} gap-[2px] ${isVertical ? "h-full w-3" : "w-full h-3"}`}
        >
            {segments.map((s, i) => (
                <div
                    key={i}
                    className="flex-1 transition-opacity duration-75"
                    style={{
                        backgroundColor: s.lit ? s.color : "#13151f",
                        opacity: s.lit ? 1 : 0.55,
                        boxShadow: s.lit ? `0 0 6px ${s.color}` : "none",
                    }}
                />
            ))}
        </div>
    );
};
