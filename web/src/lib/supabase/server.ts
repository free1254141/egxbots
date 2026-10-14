import { createClient } from "@supabase/supabase-js";
import { cookies } from "next/headers";
import type { NextRequest } from "next/server";
import { accessTokenExpiry, readAccessToken } from "./read-session";

export const createSupabaseServerClient = async (request?: NextRequest) => {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
  const key =
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY;
  if (!url || !key) throw new Error("Missing Supabase environment variables");
  const bearer = request?.headers.get("authorization");
  const token = bearer?.startsWith("Bearer ")
    ? bearer.slice(7).trim()
    : readAccessToken(request?.cookies ?? (await cookies()), url);
  // Read routes never load refresh credentials or initialize an SSR session.
  // The browser remains the sole refresh-token rotation owner.
  const client = createClient(url, key, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false,
    },
    ...(token
      ? { global: { headers: { Authorization: `Bearer ${token}` } } }
      : {}),
  });
  const getUser = client.auth?.getUser?.bind(client.auth);
  let verified: ReturnType<typeof getUser> | undefined;
  if (client.auth && getUser) {
    client.auth.getUser = ((jwt?: string) =>
      jwt && jwt !== token
        ? getUser(jwt)
        : (verified ??= getUser(
            token || undefined,
          ))) as typeof client.auth.getUser;
  }
  // Payment routes forward the access token only after verified identity.
  if (client.auth) {
    client.auth.getSession = (async () => {
    if (!token) return { data: { session: null }, error: null };
    const { data, error } = await client.auth.getUser();
    if (error || !data.user) return { data: { session: null }, error };
    const expiresAt = accessTokenExpiry(token);
    if (expiresAt !== null && expiresAt <= Date.now())
      return { data: { session: null }, error: null };
    return {
      data: {
        session: {
          access_token: token,
          refresh_token: "",
          token_type: "bearer",
          expires_in: expiresAt
            ? Math.max(0, Math.floor((expiresAt - Date.now()) / 1000))
            : 0,
          expires_at: expiresAt ? Math.floor(expiresAt / 1000) : undefined,
          user: data.user,
        },
      },
      error: null,
    };
  }) as typeof client.auth.getSession;
  }
  return client as any;
};
