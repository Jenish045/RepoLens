"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AuthCallbackPage() {
  const router = useRouter();
  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const token = params.get("token");
    window.history.replaceState(null, "", "/auth/callback");
    if (!token) { router.replace("/?error=github_sign_in_failed"); return; }
    try {
      sessionStorage.setItem("repolens_session", token);
    } catch {
      router.replace("/?error=session_storage_unavailable");
      return;
    }
    router.replace("/dashboard");
  }, [router]);
  return <main className="grid min-h-screen place-items-center bg-slate-50"><p className="text-sm text-slate-600">Completing secure sign-in…</p></main>;
}
