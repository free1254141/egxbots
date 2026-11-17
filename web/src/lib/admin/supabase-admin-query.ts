export type SupabaseQueryResult<T> = Promise<{ data: T[] | null; error: { message?: string } | null }>;

export interface PagedAuthUser {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string | null;
  is_admin: boolean;
}

const DEFAULT_PAGE_SIZE = 1000;
const MAX_SAFE_PAGES = 50;

/**
 * Paginates any Supabase PostgREST query using .range(from, to) so results are
 * never silently truncated at PostgREST's 1,000-row cap.
 */
export async function fetchAllPages<T>(
  runPage: (from: number, to: number) => SupabaseQueryResult<T>,
  pageSize = DEFAULT_PAGE_SIZE
): Promise<T[]> {
  const all: T[] = [];
  for (let page = 0; page < MAX_SAFE_PAGES; page++) {
    const from = page * pageSize;
    const to = from + pageSize - 1;
    const { data, error } = await runPage(from, to);
    if (error) {
      throw new Error(error.message || "Paginated Supabase query failed");
    }
    const batch = data || [];
    all.push(...batch);
    if (batch.length < pageSize) break;
  }
  return all;
}

/**
 * Splits large ID lists into small `.in(...)` chunks to keep PostgREST URL lengths bounded.
 */
export function chunkIds(ids: string[], size = 100): string[][] {
  const chunks: string[][] = [];
  for (let i = 0; i < ids.length; i += size) {
    chunks.push(ids.slice(i, i + size));
  }
  return chunks;
}

/**
 * Loads all auth.users pages across Supabase Auth Admin API (1,000 per page max).
 */
export async function listAllAuthUsers(
  supabase: any,
  perPage = 1000
): Promise<Map<string, PagedAuthUser>> {
  const byId = new Map<string, PagedAuthUser>();
  for (let page = 1; page <= MAX_SAFE_PAGES; page++) {
    const { data, error } = await supabase.auth.admin.listUsers({ page, perPage });
    if (error) {
      throw new Error(error.message || "Failed to list auth users");
    }
    const users: any[] = data?.users || [];
    for (const u of users) {
      const id = String(u?.id || "").trim();
      if (!id) continue;
      const meta = u?.user_metadata || {};
      byId.set(id, {
        id,
        email: String(u?.email || "").trim().toLowerCase(),
        display_name:
          (typeof meta.full_name === "string" && meta.full_name.trim()) ||
          (typeof meta.name === "string" && meta.name.trim()) ||
          (typeof meta.display_name === "string" && meta.display_name.trim()) ||
          null,
        created_at: typeof u?.created_at === "string" ? u.created_at : null,
        is_admin: u?.app_metadata?.role === "admin",
      });
    }
    if (users.length < perPage) break;
  }
  return byId;
}
