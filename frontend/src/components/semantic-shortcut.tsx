"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

export function SemanticShortcut() {
  const pathname = usePathname();
  const router = useRouter();
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        const repositoryId = pathname.match(/^\/repositories\/([^/]+)/)?.[1];
        router.push(repositoryId ? `/search/semantic?repository_id=${encodeURIComponent(repositoryId)}` : "/search/semantic");
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [pathname, router]);
  return null;
}
