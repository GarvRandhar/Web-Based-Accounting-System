"use client";

import { useState, useRef, useEffect } from "react";
import {
    Card,
    CardHeader,
    CardTitle,
    CardDescription,
    CardContent,
    CardFooter,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

import {
    Eye,
    EyeOff,
    Lock,
    Mail,
} from "lucide-react";

export interface LoginSignupProps {
    mode: "login" | "register";
    csrfToken: string;
    error?: string;
    loginUrl?: string;
    registerUrl?: string;
}

export default function LoginCardSection({
    mode = "login",
    csrfToken = "",
    error = "",
    loginUrl = "#",
    registerUrl = "#",
}: LoginSignupProps) {
    const [showPassword, setShowPassword] = useState(false);

    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    useEffect(() => {
        const canvas = canvasRef.current;
        const ctx = canvas?.getContext("2d");
        if (!canvas || !ctx) return;

        const setSize = () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        };
        setSize();

        type P = { x: number; y: number; v: number; o: number };
        let ps: P[] = [];
        let raf = 0;

        const make = () => ({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            v: Math.random() * 0.25 + 0.05,
            o: Math.random() * 0.35 + 0.15,
        });

        const init = () => {
            ps = [];
            const count = Math.floor((canvas.width * canvas.height) / 9000);
            for (let i = 0; i < count; i++) ps.push(make());
        };

        const draw = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ps.forEach((p) => {
                p.y -= p.v;
                if (p.y < 0) {
                    p.x = Math.random() * canvas.width;
                    p.y = canvas.height + Math.random() * 40;
                    p.v = Math.random() * 0.25 + 0.05;
                    p.o = Math.random() * 0.35 + 0.15;
                }
                ctx.fillStyle = `rgba(250,250,250,${p.o})`;
                ctx.fillRect(p.x, p.y, 0.7, 2.2);
            });
            raf = requestAnimationFrame(draw);
        };

        const onResize = () => {
            setSize();
            init();
        };

        window.addEventListener("resize", onResize);
        init();
        raf = requestAnimationFrame(draw);
        return () => {
            window.removeEventListener("resize", onResize);
            cancelAnimationFrame(raf);
        };
    }, []);

    return (
        <section className="fixed inset-0 bg-zinc-950 text-zinc-50">
            <style>{`
        .accent-lines{position:absolute;inset:0;pointer-events:none;opacity:.7}
        .hline,.vline{position:absolute;background:#27272a;will-change:transform,opacity}
        .hline{left:0;right:0;height:1px;transform:scaleX(0);transform-origin:50% 50%;animation:drawX .8s cubic-bezier(.22,.61,.36,1) forwards}
        .vline{top:0;bottom:0;width:1px;transform:scaleY(0);transform-origin:50% 0%;animation:drawY .9s cubic-bezier(.22,.61,.36,1) forwards}
        .hline:nth-child(1){top:18%;animation-delay:.12s}
        .hline:nth-child(2){top:50%;animation-delay:.22s}
        .hline:nth-child(3){top:82%;animation-delay:.32s}
        .vline:nth-child(4){left:22%;animation-delay:.42s}
        .vline:nth-child(5){left:50%;animation-delay:.54s}
        .vline:nth-child(6){left:78%;animation-delay:.66s}
        .hline::after,.vline::after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(250,250,250,.24),transparent);opacity:0;animation:shimmer .9s ease-out forwards}
        .hline:nth-child(1)::after{animation-delay:.12s}
        .hline:nth-child(2)::after{animation-delay:.22s}
        .hline:nth-child(3)::after{animation-delay:.32s}
        .vline:nth-child(4)::after{animation-delay:.42s}
        .vline:nth-child(5)::after{animation-delay:.54s}
        .vline:nth-child(6)::after{animation-delay:.66s}
        @keyframes drawX{0%{transform:scaleX(0);opacity:0}60%{opacity:.95}100%{transform:scaleX(1);opacity:.7}}
        @keyframes drawY{0%{transform:scaleY(0);opacity:0}60%{opacity:.95}100%{transform:scaleY(1);opacity:.7}}
        @keyframes shimmer{0%{opacity:0}35%{opacity:.25}100%{opacity:0}}

        /* === Card minimal fade-up animation === */
        .card-animate {
          opacity: 0;
          transform: translateY(20px);
          animation: fadeUp 0.8s cubic-bezier(.22,.61,.36,1) 0.4s forwards;
        }
        @keyframes fadeUp {
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>

            {/* Subtle vignette */}
            <div className="absolute inset-0 pointer-events-none [background:radial-gradient(80%_60%_at_50%_30%,rgba(255,255,255,0.06),transparent_60%)]" />

            {/* Animated accent lines */}
            <div className="accent-lines">
                <div className="hline" />
                <div className="hline" />
                <div className="hline" />
                <div className="vline" />
                <div className="vline" />
                <div className="vline" />
            </div>

            {/* Particles */}
            <canvas
                ref={canvasRef}
                className="absolute inset-0 w-full h-full opacity-50 mix-blend-screen pointer-events-none"
            />



            {/* Centered Login Card */}
            <div className="h-full w-full grid place-items-center px-4">
                <Card className="card-animate w-full max-w-sm border-zinc-800 bg-zinc-900/70 backdrop-blur supports-[backdrop-filter]:bg-zinc-900/60">
                    {error && (
                        <div className="bg-red-500/10 border-l-4 border-red-500 text-red-500 p-4 mb-4 text-sm mt-4 mx-6 rounded-r-md">
                            {error}
                        </div>
                    )}
                    <CardHeader className="space-y-1">
                        <CardTitle className="text-2xl">
                            {mode === "login" ? "Welcome back" : "Create Account"}
                        </CardTitle>
                        <CardDescription className="text-zinc-400">
                            {mode === "login" ? "Sign in to your account" : "Set up your accounting workspace"}
                        </CardDescription>
                    </CardHeader>

                    <CardContent className="grid gap-5">
                        <form method="POST" className="grid gap-5" action={mode === "login" ? loginUrl : registerUrl}>
                            <input type="hidden" name="csrf_token" value={csrfToken} />

                            <div className="grid gap-2">
                                <Label htmlFor="username" className="text-zinc-300">
                                    Username
                                </Label>
                                <div className="relative">
                                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
                                    <Input
                                        id="username"
                                        name="username"
                                        type="text"
                                        required
                                        placeholder="johndoe"
                                        className="pl-10 bg-zinc-950 border-zinc-800 text-zinc-50 placeholder:text-zinc-600"
                                    />
                                </div>
                            </div>

                            {mode === "register" && (
                                <div className="grid gap-2">
                                    <Label htmlFor="email" className="text-zinc-300">
                                        Email
                                    </Label>
                                    <div className="relative">
                                        <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
                                        <Input
                                            id="email"
                                            name="email"
                                            type="email"
                                            required
                                            placeholder="you@example.com"
                                            className="pl-10 bg-zinc-950 border-zinc-800 text-zinc-50 placeholder:text-zinc-600"
                                        />
                                    </div>
                                </div>
                            )}

                            <div className="grid gap-2">
                                <Label htmlFor="password" className="text-zinc-300">
                                    Password
                                </Label>
                                <div className="relative">
                                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
                                    <Input
                                        id="password"
                                        name="password"
                                        required
                                        type={showPassword ? "text" : "password"}
                                        placeholder="••••••••"
                                        className="pl-10 pr-10 bg-zinc-950 border-zinc-800 text-zinc-50 placeholder:text-zinc-600"
                                    />
                                    <button
                                        type="button"
                                        title={showPassword ? "Hide password" : "Show password"}
                                        aria-label={showPassword ? "Hide password" : "Show password"}
                                        className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-md text-zinc-400 hover:text-zinc-200"
                                        onClick={() => setShowPassword((v) => !v)}
                                    >
                                        {showPassword ? (
                                            <EyeOff className="h-4 w-4" />
                                        ) : (
                                            <Eye className="h-4 w-4" />
                                        )}
                                    </button>
                                </div>
                            </div>

                            {mode === "login" && (
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <Checkbox
                                            id="remember"
                                            name="remember"
                                            className="border-zinc-700 data-[state=checked]:bg-zinc-50 data-[state=checked]:text-zinc-900"
                                        />
                                        <Label htmlFor="remember" className="text-zinc-400">
                                            Remember me
                                        </Label>
                                    </div>
                                    <a href="#" className="text-sm text-zinc-300 hover:text-zinc-100">
                                        Forgot password?
                                    </a>
                                </div>
                            )}

                            <Button type="submit" className="w-full h-10 rounded-lg bg-zinc-50 text-zinc-900 hover:bg-zinc-200">
                                {mode === "login" ? "Sign In" : "Register"}
                            </Button>
                        </form>


                    </CardContent>

                    <CardFooter className="flex items-center justify-center text-sm text-zinc-400 pb-6 pt-0">
                        {mode === "login" ? (
                            <>
                                Don’t have an account?
                                <a className="ml-1 text-zinc-200 hover:underline" href={registerUrl}>
                                    Create one
                                </a>
                            </>
                        ) : (
                            <>
                                Already have an account?
                                <a className="ml-1 text-zinc-200 hover:underline" href={loginUrl}>
                                    Sign in
                                </a>
                            </>
                        )}
                    </CardFooter>
                </Card>
            </div>
        </section>
    );
}
