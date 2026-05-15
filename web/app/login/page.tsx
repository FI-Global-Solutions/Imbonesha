"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import axios from "axios";
import { toast } from "sonner";
import {
  Loader2,
  Mail,
  Lock,
  ArrowRight,
  Satellite,
  ShieldCheck,
  Map,
} from "lucide-react";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ThemeToggle } from "@/components/theme-toggle";
import { setCookie } from "@/lib/api/client";

const schema = z.object({
  email: z.string().email("Valid email required"),
  password: z.string().min(1, "Password required"),
});

type FormData = z.infer<typeof schema>;

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8007";

const FEATURES = [
  {
    icon: Satellite,
    label: "Satellite change detection",
    desc: "AI-powered analysis of before/after imagery",
  },
  {
    icon: ShieldCheck,
    label: "Permit verification",
    desc: "Cross-referenced against the national registry",
  },
  {
    icon: Map,
    label: "Live violation map",
    desc: "Real-time flags across all districts",
  },
];

export default function LoginPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: FormData) => {
    setLoading(true);
    try {
      const res = await axios.post(`${API_URL}/api/v1/auth/login/`, {
        email: data.email,
        password: data.password,
      });
      setCookie("access_token", res.data.access, 60 * 60 * 8);
      setCookie("refresh_token", res.data.refresh, 60 * 60 * 24 * 7);
      router.push("/");
    } catch {
      toast.error("Invalid credentials", {
        description: "Check your email and password and try again.",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-background">
      {/* ── Left panel — branding ───────────────────────────────────────── */}
      <div className="hidden lg:flex lg:w-[52%] flex-col relative overflow-hidden bg-[#0a1f12]">
        {/* Subtle grid texture */}
        <div className="absolute inset-0 opacity-[0.04] login-grid-texture" />

        {/* Green radial glow */}
        <div className="absolute -top-40 -left-40 w-[600px] h-[600px] rounded-full bg-primary/20 blur-[120px] pointer-events-none" />
        <div className="absolute bottom-0 right-0 w-[400px] h-[400px] rounded-full bg-primary/10 blur-[100px] pointer-events-none" />

        {/* Content */}
        <div className="relative z-10 flex flex-col h-full px-12 py-10">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-primary/20 border border-primary/30 flex items-center justify-center overflow-hidden">
              <Image
                src="/logo.png"
                alt="Imbonesha"
                width={30}
                height={30}
                className="object-contain"
                priority
              />
            </div>
            <div>
              <p className="text-white font-bold text-[15px] leading-none">
                Imbonesha
              </p>
              <p className="text-primary/70 text-[10px] font-semibold uppercase tracking-widest mt-0.5">
                RHA · Rwanda
              </p>
            </div>
          </div>

          {/* Hero text */}
          <div className="mt-auto mb-auto pt-16">
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 mb-6">
              <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
              <span className="text-primary text-[11px] font-semibold uppercase tracking-widest">
                Live monitoring
              </span>
            </div>

            <h1 className="text-4xl font-bold text-white leading-[1.15] tracking-tight">
              Detect unauthorized
              <br />
              <span className="text-primary">construction</span>
              <br />
              before it's too late.
            </h1>

            <p className="mt-5 text-white/50 text-sm leading-relaxed max-w-sm">
              Imbonesha uses satellite imagery and machine learning to
              automatically detect and flag unauthorized building activity
              across Rwanda.
            </p>

            {/* Feature list */}
            <div className="mt-10 space-y-4">
              {FEATURES.map(({ icon: Icon, label, desc }) => (
                <div key={label} className="flex items-start gap-3.5">
                  <div className="h-8 w-8 rounded-lg bg-primary/15 border border-primary/20 flex items-center justify-center shrink-0 mt-0.5">
                    <Icon className="h-3.5 w-3.5 text-primary" />
                  </div>
                  <div>
                    <p className="text-white text-sm font-medium leading-none">
                      {label}
                    </p>
                    <p className="text-white/40 text-xs mt-1">{desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Footer */}
          <p className="text-white/20 text-[11px]">
            © {new Date().getFullYear()} Rwanda Housing Authority. All rights
            reserved.
          </p>
        </div>
      </div>

      {/* ── Right panel — form ──────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-12 relative">
        <div className="absolute top-4 right-4">
          <ThemeToggle />
        </div>

        {/* Mobile logo (hidden on desktop) */}
        <div className="lg:hidden flex flex-col items-center gap-3 mb-10">
          <div className="h-16 w-16 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center overflow-hidden">
            <Image
              src="/logo.png"
              alt="Imbonesha"
              width={48}
              height={48}
              className="object-contain"
              priority
            />
          </div>
          <div className="text-center">
            <p className="font-bold text-lg">Imbonesha</p>
            <p className="text-xs text-muted-foreground">
              Rwanda Housing Authority
            </p>
          </div>
        </div>

        <div className="w-full max-w-[380px]">
          {/* Heading */}
          <div className="mb-8">
            <h2 className="text-2xl font-bold tracking-tight">Welcome back</h2>
            <p className="text-muted-foreground text-sm mt-1.5">
              Sign in to your RHA monitoring account
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
            {/* Email */}
            <div className="space-y-1.5">
              <Label htmlFor="email" className="text-sm font-medium">
                Email address
              </Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                <Input
                  id="email"
                  type="email"
                  placeholder="you@rha.gov.rw"
                  autoComplete="email"
                  className="pl-9 h-11"
                  {...register("email")}
                />
              </div>
              {errors.email && (
                <p className="text-xs text-destructive">
                  {errors.email.message}
                </p>
              )}
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <Label htmlFor="password" className="text-sm font-medium">
                Password
              </Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  className="pl-9 pr-16 h-11"
                  {...register("password")}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] font-semibold text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
              {errors.password && (
                <p className="text-xs text-destructive">
                  {errors.password.message}
                </p>
              )}
            </div>

            {/* Submit */}
            <Button
              type="submit"
              className="w-full h-11 text-sm font-semibold gap-2 mt-2"
              disabled={loading}
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Signing in…
                </>
              ) : (
                <>
                  Sign in
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </Button>
          </form>

          {/* Demo credentials
          <div className="mt-8 rounded-xl border border-border bg-muted/40 px-4 py-3.5">
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest mb-2">
              Demo credentials
            </p>
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Email</span>
                <span className="text-xs font-mono font-medium">demo@imbonesha.gov.rw</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Password</span>
                <span className="text-xs font-mono font-medium">Demo2026!</span>
              </div>
            </div>
          </div> */}
        </div>
      </div>
    </div>
  );
}
