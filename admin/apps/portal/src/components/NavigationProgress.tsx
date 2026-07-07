"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";

// A global top-of-viewport progress bar that gives immediate feedback on every
// client-side navigation. App Router has no router events, so we start the bar
// on the navigation trigger (an internal anchor click, or back/forward) and
// complete it when the committed pathname/search settles.
const TRICKLE_CEILING = 90;

export function NavigationProgress() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [width, setWidth] = useState(0);
  const [active, setActive] = useState(false);

  // Timers and the "are we mid-navigation" flag live in refs so the start
  // (event listeners, mounted once) and finish (pathname effect) paths share
  // them without re-binding listeners.
  const trickle = useRef<ReturnType<typeof setInterval> | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const safety = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loading = useRef(false);

  const clearTimers = () => {
    if (trickle.current) clearInterval(trickle.current);
    if (hideTimer.current) clearTimeout(hideTimer.current);
    if (safety.current) clearTimeout(safety.current);
    trickle.current = null;
    hideTimer.current = null;
    safety.current = null;
  };

  const finish = () => {
    if (!loading.current) return;
    loading.current = false;
    clearTimers();
    setWidth(100);
    hideTimer.current = setTimeout(() => {
      setActive(false);
      // Reset width only after the fade-out so the bar doesn't visibly rewind.
      hideTimer.current = setTimeout(() => setWidth(0), 220);
    }, 180);
  };

  const start = () => {
    if (loading.current) return;
    loading.current = true;
    clearTimers();
    setActive(true);
    setWidth(8);
    // Ease toward the ceiling with ever-smaller steps so the bar keeps moving
    // while the server work is in flight but never reaches 100% on its own.
    trickle.current = setInterval(() => {
      setWidth((w) => (w >= TRICKLE_CEILING ? w : w + Math.max(0.4, (TRICKLE_CEILING - w) * 0.12)));
    }, 220);
    // Never leave the bar stuck if a navigation is cancelled or never commits.
    safety.current = setTimeout(finish, 12000);
  };

  // Start triggers: capture anchor clicks before navigation, and back/forward.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const anchor = (e.target as HTMLElement | null)?.closest?.("a");
      if (!anchor) return;
      const href = anchor.getAttribute("href");
      const target = anchor.getAttribute("target");
      if (!href || (target && target !== "_self")) return;
      if (anchor.hasAttribute("download")) return;
      if (/^(https?:|mailto:|tel:|#)/.test(href) && !href.startsWith(location.origin)) {
        if (href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) return;
      }
      let url: URL;
      try {
        url = new URL(anchor.href, location.href);
      } catch {
        return;
      }
      if (url.origin !== location.origin) return;
      // Same-page link (hash or identical URL) → no navigation to track.
      if (url.pathname === location.pathname && url.search === location.search) return;
      start();
    };
    document.addEventListener("click", onClick, true);
    window.addEventListener("popstate", start);
    return () => {
      document.removeEventListener("click", onClick, true);
      window.removeEventListener("popstate", start);
      clearTimers();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Finish trigger: the route committed (pathname or query changed). The
  // guard in finish() makes the mount-time run a no-op.
  useEffect(() => {
    finish();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, searchParams]);

  return (
    <div className="nav-progress" data-active={active} aria-hidden="true">
      <div className="nav-progress__bar" style={{ width: `${width}%` }} />
    </div>
  );
}
