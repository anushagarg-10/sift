"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, type AppConfig } from "@/lib/api";

function NavLinks({ pathname }: { pathname: string | null }) {
  const isEvals = pathname?.startsWith("/evals") ?? false;
  return (
    <nav className="nav">
      <Link href="/" className={pathname && !isEvals ? "active" : ""}>
        Datasets
      </Link>
      <Link href="/evals" className={isEvals ? "active" : ""}>
        Evals
      </Link>
    </nav>
  );
}

function ActiveNavLinks() {
  return <NavLinks pathname={usePathname()} />;
}

export function Nav() {
  const [config, setConfig] = useState<AppConfig | null>(null);

  useEffect(() => {
    api
      .config()
      .then(setConfig)
      .catch(() => setConfig(null));
  }, []);

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Link href="/" className="brand">
          <span className="brand-dot" aria-hidden />
          Sift
        </Link>
        {/* The pathname is only known at request time on dynamic routes, so stream it in. */}
        <Suspense fallback={<NavLinks pathname={null} />}>
          <ActiveNavLinks />
        </Suspense>
        <div className="spacer" />
        {config && (
          <span className="badge accent model-badge" title="Active LLM provider">
            {config.provider} · <span className="mono">{config.model}</span>
          </span>
        )}
      </div>
    </header>
  );
}
