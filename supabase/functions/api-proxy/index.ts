import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

import { rewriteProxySetCookie } from "./cookies.ts";
import { buildForwardHeaders, getCorsHeaders, normalizeProxyPath } from "./contract.ts";

const API_BASE = "https://api.poe.lama-lan.ch";
const DEBUG_TRAFFIC_CAPTURE = Deno.env.get("ENABLE_DEBUG_TRAFFIC_CAPTURE") === "true";

// Paths that require the admin role (ops-only)
const ADMIN_PATH_PREFIXES = [
  "/api/v1/ops/",
  "/api/v1/actions/",
];

// Public endpoints that don't require auth
const PUBLIC_PATH_PATTERNS = [
  /^\/healthz$/,
  /^\/api\/v1\/ops\/leagues\/[^/]+\/price-check/,
  /^\/api\/v1\/ml\/leagues\/[^/]+\/predict-one/,
  /^\/api\/v1\/auth\//,
  /^\/api\/v1\/stash\//,
];

function isPublicEndpoint(path: string): boolean {
  return PUBLIC_PATH_PATTERNS.some((p) => p.test(path));
}

function isAdminPath(path: string): boolean {
  return ADMIN_PATH_PREFIXES.some((p) => path.startsWith(p));
}

// Debug: save request/response to debug_traffic table
async function captureTraffic(
  method: string,
  path: string,
  reqHeaders: Record<string, string>,
  reqBody: string | undefined,
  resStatus: number,
  resHeaders: Record<string, string>,
  resBody: string,
) {
  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const sb = createClient(supabaseUrl, serviceRoleKey);
    await sb.from("debug_traffic").insert({
      method,
      path,
      request_headers: reqHeaders,
      request_body: reqBody ?? null,
      response_status: resStatus,
      response_headers: resHeaders,
      response_body: resBody,
    });
    console.log(`[api-proxy] DEBUG captured ${method} ${path} (${resBody.length} bytes)`);
  } catch (e) {
    console.error(`[api-proxy] DEBUG capture failed:`, e);
  }
}

Deno.serve(async (req) => {
  const corsHeaders = getCorsHeaders(req);

  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  // 0. Get and validate the target path
  const rawPath = req.headers.get("x-proxy-path");
  if (!rawPath) {
    return new Response(JSON.stringify({ error: "Missing x-proxy-path header" }), {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const proxyPath = normalizeProxyPath(rawPath);
  if (!proxyPath) {
    return new Response(JSON.stringify({ error: "Forbidden path" }), {
      status: 403,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  // 1. Validate Supabase JWT (skip for public endpoints)
  const authHeader = req.headers.get("authorization");

  if (!isPublicEndpoint(proxyPath)) {
    if (!authHeader) {
      return new Response(JSON.stringify({ error: "Missing authorization" }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseAnonKey = Deno.env.get("SUPABASE_ANON_KEY")!;
    const supabase = createClient(supabaseUrl, supabaseAnonKey, {
      global: { headers: { Authorization: authHeader } },
    });

    const {
      data: { user },
      error: userError,
    } = await supabase.auth.getUser();

    if (userError || !user) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // 2. Check approval status
    const { data: approval } = await supabase
      .from("approved_users")
      .select("id")
      .eq("user_id", user.id)
      .maybeSingle();

    if (!approval) {
      return new Response(JSON.stringify({ error: "Account not approved" }), {
        status: 403,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // 3. Enforce admin role for ops/actions paths
    if (isAdminPath(proxyPath)) {
      const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
      const adminSb = createClient(supabaseUrl, serviceRoleKey);
      const { data: roleRow } = await adminSb
        .from("user_roles")
        .select("role")
        .eq("user_id", user.id)
        .eq("role", "admin")
        .maybeSingle();

      if (!roleRow) {
        return new Response(JSON.stringify({ error: "Forbidden" }), {
          status: 403,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }
    }
  }

  // 4. Forward request to backend with server-side API key
  const apiKey = Deno.env.get("VITE_API_KEY");
  const targetUrl = `${API_BASE}${proxyPath}`;

  const forwardHeaders = buildForwardHeaders({
    existingCookie: req.headers.get("cookie") || "",
  });
  if (apiKey) {
    forwardHeaders["Authorization"] = `Bearer ${apiKey}`;
  }

  try {
    const body = req.method !== "GET" && req.method !== "HEAD" ? await req.text() : undefined;

    console.log(`[api-proxy] ${req.method} ${targetUrl}`);

    const backendRes = await fetch(targetUrl, {
      method: req.method,
      headers: forwardHeaders,
      body,
      // Forward the client's abort signal so cancelling on the frontend
      // also cancels the in-flight backend request immediately.
      signal: req.signal,
    });

    console.log(`[api-proxy] backend responded ${backendRes.status}`);

    const responseHeaders = new Headers(corsHeaders);
    responseHeaders.set("Content-Type", backendRes.headers.get("Content-Type") || "application/json");

    // Forward set-cookie from backend
    const setCookie = backendRes.headers.get("set-cookie");
    if (setCookie) {
      responseHeaders.set("set-cookie", rewriteProxySetCookie(setCookie));
    }

    if (DEBUG_TRAFFIC_CAPTURE) {
      const backendCopy = backendRes.clone();
      const fwdHeadersObj: Record<string, string> = {};
      for (const [k, v] of Object.entries(forwardHeaders)) fwdHeadersObj[k] = v;
      const resHeadersObj: Record<string, string> = {};
      backendRes.headers.forEach((v, k) => { resHeadersObj[k] = v; });
      void (async () => {
        try {
          const bodyText = await backendCopy.text();
          await captureTraffic(req.method, proxyPath, fwdHeadersObj, body, backendRes.status, resHeadersObj, bodyText);
        } catch (e) {
          console.error(`[api-proxy] DEBUG capture failed:`, e);
        }
      })();
    }

    return new Response(backendRes.body, {
      status: backendRes.status,
      headers: responseHeaders,
    });
  } catch (err) {
    console.error(`[api-proxy] fetch error:`, err);
    return new Response(
      JSON.stringify({ error: "Service unavailable" }),
      { status: 502, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
