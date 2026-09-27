import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";
import { SemanticShortcut } from "@/components/semantic-shortcut";

export const metadata: Metadata = {
  title: "RepoLens",
  description: "Understand software systems, not just source code.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased"><SemanticShortcut />{children}</body>
    </html>
  );
}
