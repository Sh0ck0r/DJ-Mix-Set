/** @type {import('tailwindcss').Config} */
module.exports = {
    darkMode: ["class"],
    content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
    theme: {
        extend: {
            fontFamily: {
                display: ['Unbounded', 'sans-serif'],
                mono: ['"JetBrains Mono"', 'monospace'],
                ui: ['Chivo', 'sans-serif'],
            },
            borderRadius: {
                lg: 'var(--radius)',
                md: 'calc(var(--radius) - 2px)',
                sm: 'calc(var(--radius) - 4px)',
            },
            colors: {
                background: 'hsl(var(--background))',
                foreground: 'hsl(var(--foreground))',
                card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
                popover: { DEFAULT: 'hsl(var(--popover))', foreground: 'hsl(var(--popover-foreground))' },
                primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
                secondary: { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--secondary-foreground))' },
                muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
                accent: { DEFAULT: 'hsl(var(--accent))', foreground: 'hsl(var(--accent-foreground))' },
                destructive: { DEFAULT: 'hsl(var(--destructive))', foreground: 'hsl(var(--destructive-foreground))' },
                border: 'hsl(var(--border))',
                input: 'hsl(var(--input))',
                ring: 'hsl(var(--ring))',
                neon: {
                    cyan: '#00F0FF',
                    green: '#39FF14',
                    red: '#FF003C',
                    yellow: '#F2E900',
                },
                surface: {
                    DEFAULT: '#0D0E15',
                    hover: '#161824',
                    dark: '#050505',
                },
            },
            keyframes: {
                'accordion-down': { from: { height: '0' }, to: { height: 'var(--radix-accordion-content-height)' } },
                'accordion-up': { from: { height: 'var(--radix-accordion-content-height)' }, to: { height: '0' } },
                'pulse-glow': {
                    '0%, 100%': { boxShadow: '0 0 12px rgba(0,240,255,0.4)' },
                    '50%': { boxShadow: '0 0 28px rgba(0,240,255,0.9)' },
                },
                'scan-line': {
                    '0%': { transform: 'translateY(-100%)' },
                    '100%': { transform: 'translateY(100%)' },
                },
                'flicker': {
                    '0%, 100%': { opacity: '1' },
                    '45%': { opacity: '1' },
                    '50%': { opacity: '0.6' },
                    '55%': { opacity: '1' },
                },
                'marquee': {
                    '0%': { transform: 'translateX(0%)' },
                    '100%': { transform: 'translateX(-50%)' },
                },
            },
            animation: {
                'accordion-down': 'accordion-down 0.2s ease-out',
                'accordion-up': 'accordion-up 0.2s ease-out',
                'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
                'scan-line': 'scan-line 4s linear infinite',
                'flicker': 'flicker 3s linear infinite',
                'marquee': 'marquee 20s linear infinite',
            },
        },
    },
    plugins: [require("tailwindcss-animate")],
};
