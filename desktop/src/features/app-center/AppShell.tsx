import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { featureFlags } from "../../featureFlags";

type HashRouterValue = {
  pathname: string;
  navigate: (pathname: string) => void;
};

const HashRouterContext = createContext<HashRouterValue | null>(null);
const LAST_ROUTE_STORAGE_KEY = "pixelle_app_center_last_route";
const LAST_PUBLISH_HANDOFF_STORAGE_KEY = "pixelle_app_center_last_publish_handoff";
const ROUTES = new Set([
  "/apps",
  "/apps/digital-human-video",
  "/home",
  "/ip",
  "/assets",
  "/publish",
  "/tasks",
  "/config",
  "/diagnostics",
  "/settings",
  "/projects",
  "/runs",
]);

function normalizePath(pathname: string) {
  const [basePath, rawQuery = ""] = pathname.split("?", 2);
  if (!ROUTES.has(basePath)) return "/apps";
  if (basePath !== "/publish" || !rawQuery) return basePath;
  const params = new URLSearchParams(rawQuery);
  const allowed = new Set(["package_id", "artifact_id", "run_id"]);
  if ([...params.keys()].some((key) => !allowed.has(key) || !params.get(key))) return "/apps";
  return `${basePath}?${params.toString()}`;
}

function isPublishHandoff(pathname: string) {
  return pathname.startsWith("/publish?");
}

function rememberPublishHandoff(pathname: string) {
  if (typeof window !== "undefined" && isPublishHandoff(pathname)) {
    window.localStorage.setItem(LAST_PUBLISH_HANDOFF_STORAGE_KEY, pathname);
  }
}

function resolveNavigationPath(pathname: string) {
  const normalized = normalizePath(pathname);
  if (normalized !== "/publish" || typeof window === "undefined") return normalized;
  const handoff = window.localStorage.getItem(LAST_PUBLISH_HANDOFF_STORAGE_KEY);
  if (!handoff) return normalized;
  const remembered = normalizePath(handoff);
  return isPublishHandoff(remembered) ? remembered : normalized;
}

function readHashPath() {
  if (typeof window === "undefined") return "/apps";
  const raw = window.location.hash.replace(/^#/, "");
  if (!raw || raw === "/") {
    const stored = window.localStorage.getItem(LAST_ROUTE_STORAGE_KEY);
    return stored && stored.startsWith("/") ? normalizePath(stored) : "/apps";
  }
  return normalizePath(raw.startsWith("/") ? raw : `/${raw}`);
}

export function HashRouter({ children }: { children: ReactNode }) {
  const [pathname, setPathname] = useState(readHashPath);

  useEffect(() => {
    const onHashChange = () => {
      const nextPathname = readHashPath();
      rememberPublishHandoff(nextPathname);
      window.localStorage.setItem(LAST_ROUTE_STORAGE_KEY, nextPathname);
      setPathname(nextPathname);
    };
    window.addEventListener("hashchange", onHashChange);
    const initialPathname = readHashPath();
    rememberPublishHandoff(initialPathname);
    window.localStorage.setItem(LAST_ROUTE_STORAGE_KEY, initialPathname);
    const rawHash = window.location.hash.replace(/^#/, "");
    const rawHashPath = rawHash.startsWith("/") ? rawHash : rawHash ? `/${rawHash}` : "";
    if (rawHashPath !== initialPathname) window.history.replaceState(null, "", `#${initialPathname}`);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const value = useMemo<HashRouterValue>(
    () => ({
      pathname,
      navigate: (nextPathname) => {
        const normalized = resolveNavigationPath(nextPathname.startsWith("/") ? nextPathname : `/${nextPathname}`);
        rememberPublishHandoff(normalized);
        window.localStorage.setItem(LAST_ROUTE_STORAGE_KEY, normalized);
        if (readHashPath() === normalized) {
          setPathname(normalized);
          return;
        }
        window.location.hash = normalized;
      },
    }),
    [pathname],
  );

  return <HashRouterContext.Provider value={value}>{children}</HashRouterContext.Provider>;
}

export function useHashRouter() {
  return useContext(HashRouterContext);
}

/**
 * AC-1 shell gate. The legacy StudioApp remains the exact fallback while the
 * rollout flag is disabled; enabling it only adds hash navigation state.
 */
export function AppShell({ children }: { children: ReactNode }) {
  if (!featureFlags.appCenterShell) return <>{children}</>;
  return <HashRouter>{children}</HashRouter>;
}
