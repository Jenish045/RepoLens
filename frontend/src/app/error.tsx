"use client";

import { useEffect } from "react";

export default function ErrorBoundary({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("RepoLens application boundary caught an error", error);
  }, [error]);

  return (
    <main className="mx-auto max-w-6xl px-6 py-16" role="alert">
      <h1 className="text-xl font-semibold">Something went wrong</h1>
      <p className="mt-2 text-slate-600">The page could not be displayed. Please try again.</p>
      <button className="mt-6 rounded-md border bg-white px-4 py-2 text-sm font-medium" onClick={reset}>Try again</button>
    </main>
  );
}
