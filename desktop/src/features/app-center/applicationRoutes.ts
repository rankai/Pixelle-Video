const APPLICATION_ROUTES = {
  "builtin.marketing-copy": "/apps/marketing-copy",
  "builtin.viral-titles": "/apps/viral-titles",
  "builtin.douyin-carousel": "/apps/douyin-carousel",
  "builtin.digital-human-video": "/apps/digital-human-video",
} as const;

export function applicationRouteForId(appId: string): string {
  return APPLICATION_ROUTES[appId as keyof typeof APPLICATION_ROUTES] || "/apps";
}

export function applicationIdForRoute(pathname: string): string | null {
  const basePath = pathname.split("?", 1)[0];
  return Object.entries(APPLICATION_ROUTES)
    .find(([, route]) => route === basePath)?.[0] || null;
}
