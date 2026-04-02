const ALLOWED_ORIGINS = [
  "https://poe-frontend.lovable.app",
  "https://id-preview--4f7be476-8f8c-46dd-8a65-a084f790c20d.lovable.app",
  "https://poe.lama-lan.ch",
];

export function getCorsHeaders(req: Request): Record<string, string> {
  const origin = req.headers.get("origin") || "";
  const allowedOrigin = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allowedOrigin,
    "Access-Control-Allow-Headers":
      "authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version, x-proxy-path, x-poe-backend-session",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
    "Access-Control-Allow-Credentials": "true",
  };
}

export function buildForwardHeaders(params: {
  existingCookie: string;
}): Record<string, string> {
  const forwardHeaders: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (params.existingCookie) {
    forwardHeaders["Cookie"] = params.existingCookie;
  }
  return forwardHeaders;
}

export function normalizeProxyPath(raw: string): string | null {
  if (raw.includes("..") || /%2e/i.test(raw)) {
    return null;
  }
  if (raw === "/healthz") return raw;
  if (!raw.startsWith("/api/v1/")) return null;
  try {
    const normalised = new URL(raw, "https://api.poe.lama-lan.ch");
    if (!normalised.pathname.startsWith("/api/v1/")) return null;
    return `${normalised.pathname}${normalised.search}`;
  } catch {
    return null;
  }
}
