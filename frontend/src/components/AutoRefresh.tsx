"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Atualiza a tela sozinha enquanto ela está visível. Campos digitados não são perdidos. */
export function AutoRefresh({ active }: { active: boolean }) {
  const router = useRouter();
  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") router.refresh();
    }, active ? 3000 : 20000);
    return () => clearInterval(timer);
  }, [active, router]);
  return null;
}
