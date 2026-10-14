type CookieReader = { get: (name: string) => { value: string } | undefined };
/** Decode only the access credential. Cookie claims never establish identity. */
export function readAccessToken(
  store: CookieReader,
  supabaseUrl: string,
): string | null {
  try {
    const name = `sb-${new URL(supabaseUrl).hostname.split(".")[0]}-auth-token`;
    let raw = store.get(name)?.value;
    if (!raw) {
      const parts: string[] = [];
      for (let i = 0; i < 64; i++) {
        const chunk = store.get(`${name}.${i}`)?.value;
        if (chunk === undefined) break;
        parts.push(chunk);
      }
      raw = parts.join("");
    }
    if (!raw || raw.length > 65536) return null;
    const json = raw.startsWith("base64-")
      ? Buffer.from(raw.slice(7), "base64url").toString("utf8")
      : raw;
    const session = JSON.parse(json);
    return session &&
      typeof session.access_token === "string" &&
      session.access_token.length > 0 &&
      session.access_token.length <= 16384
      ? session.access_token
      : null;
  } catch {
    return null;
  }
}
/** Expiry is a fail-closed cache bound only, never proof of authentication. */
export function accessTokenExpiry(token: string): number | null {
  try {
    const body = JSON.parse(
      Buffer.from(token.split(".")[1], "base64url").toString("utf8"),
    );
    return Number.isFinite(body.exp) && body.exp > 0 ? body.exp * 1000 : null;
  } catch {
    return null;
  }
}
