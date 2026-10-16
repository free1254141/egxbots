#!/usr/bin/env python3
"""
StokScan AI — Full Local Supabase Backup Utility
================================================
Creates a complete local backup of the Supabase database (`gfcmaxbtscmizsakarvc`):
1. If `SUPABASE_DB_URL` / `DATABASE_URL` and `pg_dump` are available, optionally runs native `pg_dump`.
2. Always supports full local backup via `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`:
   - Exports all 57 `public.*` tables using deterministic primary-key pagination.
   - Exports `auth.users` via the Supabase Auth Admin API (or pre-exported SQL snapshot).
   - Generates a complete, pg_dump-compatible SQL file (`full_backup.sql` + `full_backup.sql.gz`)
     containing DDL (schema, functions, views, triggers, indexes, RLS policies) + COPY/INSERT data.
   - Saves structured JSONL table snapshots (`tables/*.jsonl.gz`) and `backup_manifest.json`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKUPS_ROOT = ROOT_DIR / "backups"

# All 57 public tables and their deterministic primary key ordering columns
PUBLIC_TABLES_PK: Dict[str, str] = {
    "admin_access_logs": "id",
    "ai_analytics": "id",
    "ai_chat_facts": "id",
    "ai_chat_idempotency": "user_id,client_message_id",
    "ai_chat_messages": "id",
    "ai_chat_sessions": "id",
    "ai_chatbot_limits": "user_id,date",
    "ai_chatbot_logs": "id",
    "ai_chatbot_settings": "id",
    "articles": "id",
    "backtests": "id",
    "bot_alerts": "id",
    "bot_configs": "bot_id",
    "bot_daily_performance": "id",
    "bot_logs": "id",
    "bot_states": "bot_id",
    "bot_subscriptions": "id",
    "bot_trades": "id",
    "chart_drawings": "id",
    "coins": "id",
    "corporate_actions": "id",
    "daily_job_runs": "id",
    "daily_social_publications": "session_date,platform",
    "daily_social_reports": "session_date,kind",
    "data_sync_logs": "id",
    "founders_offer_members": "user_id",
    "kashier_payments": "id",
    "local_billing_settings": "id",
    "local_payment_orders": "id",
    "market_cache": "cache_key,country",
    "market_heatmap": "id",
    "model_metadata": "name",
    "payment_entitlement_events": "payment_order_id",
    "position_events": "id",
    "positions": "id",
    "pricing_plans": "id",
    "pro_telegram_invites": "user_id",
    "pro_telegram_revocations": "user_id,telegram_user_id",
    "profiles": "id",
    "public_models_config": "filename",
    "recommendation_events": "id",
    "recommendations": "id",
    "scan_results": "id",
    "shared_chat_posts": "id",
    "short_swing_checkpoints": "checkpoint_key",
    "similarity_cases": "id",
    "similarity_reports": "id",
    "social_publication_monthly_quota": "month",
    "stock_fundamentals": "symbol,exchange",
    "stock_news_sentiment": "id",
    "stock_prices": "symbol,exchange,date",
    "stock_scans_summary": "id",
    "stock_technical_indicators": "symbol,exchange,date",
    "subscriptions": "id",
    "support_messages": "id",
    "user_activity_events": "id",
    "user_settings": "user_id",
}

CORE_TABLES_ONLY = [
    "profiles",
    "user_settings",
    "pricing_plans",
    "subscriptions",
    "founders_offer_members",
    "positions",
    "position_events",
    "local_payment_orders",
    "payment_entitlement_events",
    "local_billing_settings",
    "kashier_payments",
    "pro_telegram_invites",
    "pro_telegram_revocations",
    "bot_configs",
    "bot_states",
    "bot_subscriptions",
    "public_models_config",
    "model_metadata",
    "ai_chatbot_settings",
    "ai_chatbot_limits",
    "ai_chat_sessions",
    "ai_chat_messages",
    "ai_chat_facts",
    "shared_chat_posts",
    "chart_drawings",
    "articles",
    "support_messages",
    "social_publication_monthly_quota",
    "daily_social_reports",
    "daily_social_publications",
    "short_swing_checkpoints",
]


def extract_mcp_json(file_path: Path) -> Any:
    """Extracts JSON payload from MCP execute_sql step output files."""
    if not file_path.exists():
        return None
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    res_str = raw.get("result", "")
    match = re.search(r"<untrusted-data-[^>]+>\n(.*?)\n</untrusted-data-[^>]+>", res_str, re.DOTALL)
    if not match:
        return None
    return json.loads(match.group(1))


def sql_literal(val: Any, col_type: Optional[str] = None) -> str:
    """Formats a Python value into a safe PostgreSQL SQL literal for INSERT statements."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, (dict, list)):
        if col_type and col_type.endswith("[]") and isinstance(val, list):
            # PostgreSQL array literal via ARRAY[...] or JSON cast
            if len(val) == 0:
                return f"'{{}}'::{col_type}"
            inner = ", ".join(sql_literal(v) for v in val)
            return f"ARRAY[{inner}]::{col_type}"
        json_str = json.dumps(val, ensure_ascii=False).replace("'", "''")
        cast = f"::{col_type}" if col_type in ("jsonb", "json") else "::jsonb"
        return f"'{json_str}'{cast}"
    s = str(val).replace("'", "''")
    return f"'{s}'"


def fetch_rest_table(
    supabase_url: str,
    service_key: str,
    table: str,
    pk_cols: str,
    page_size: int = 1000,
) -> List[Dict[str, Any]]:
    """Fetches all rows from a public table using deterministic pagination."""
    order_clause = ",".join(f"{c}.asc" for c in pk_cols.split(","))
    rows: List[Dict[str, Any]] = []
    offset = 0

    while True:
        query_url = (
            f"{supabase_url}/rest/v1/{table}"
            f"?select=*&order={urllib.parse.quote(order_clause)}&limit={page_size}&offset={offset}"
        )
        req = urllib.request.Request(
            query_url,
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Accept": "application/json",
            },
        )
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    batch = json.loads(resp.read().decode("utf-8"))
                break
            except Exception as exc:
                if attempt == 3:
                    raise RuntimeError(f"Failed fetching {table} at offset {offset}: {exc}") from exc
                time.sleep(1.5 * (attempt + 1))

        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    return rows


def fetch_auth_users_admin_api(supabase_url: str, service_key: str) -> List[Dict[str, Any]]:
    """Fetches all users from Supabase Auth Admin API as fallback when SQL snapshot is absent."""
    users: List[Dict[str, Any]] = []
    page = 1
    per_page = 500
    while True:
        url = f"{supabase_url}/auth/v1/admin/users?page={page}&per_page={per_page}"
        req = urllib.request.Request(
            url,
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        batch = payload.get("users", [])
        if not batch:
            break
        users.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return users


def write_sql_inserts_for_table(
    sql_fp: Any,
    schema_name: str,
    table_name: str,
    rows: List[Dict[str, Any]],
    col_types: Dict[str, str],
    batch_size: int = 250,
) -> None:
    """Writes batched INSERT statements for a table into the SQL dump file."""
    if not rows:
        sql_fp.write(f"-- Table {schema_name}.{table_name}: 0 rows\n\n")
        return

    cols = list(rows[0].keys())
    quoted_cols = ", ".join(f'"{c}"' for c in cols)
    sql_fp.write(f"--\n-- Data for Name: {table_name}; Type: TABLE DATA; Schema: {schema_name}\n--\n")
    sql_fp.write(f"-- Total rows: {len(rows)}\n")

    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        sql_fp.write(f'INSERT INTO {schema_name}."{table_name}" ({quoted_cols}) VALUES\n')
        value_lines = []
        for r in chunk:
            vals = [sql_literal(r.get(c), col_types.get(c)) for c in cols]
            value_lines.append(f"  ({', '.join(vals)})")
        sql_fp.write(",\n".join(value_lines))
        sql_fp.write("\nON CONFLICT DO NOTHING;\n")
    sql_fp.write("\n")


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def try_native_pg_dump(db_url: str, output_dir: Path) -> Optional[Path]:
    """Runs native pg_dump if pg_dump is installed and SUPABASE_DB_URL is set."""
    pg_dump_bin = shutil.which("pg_dump")
    if not pg_dump_bin:
        return None
    dump_file = output_dir / "native_pg_dump.sql"
    cmd = [
        pg_dump_bin,
        db_url,
        "--no-owner",
        "--no-privileges",
        "--schema=public",
        "--schema=auth",
        "--file",
        str(dump_file),
    ]
    print(f"[backup] Running native pg_dump -> {dump_file} ...")
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode == 0 and dump_file.exists():
        return dump_file
    print(f"[backup] Native pg_dump failed (code {res.returncode}): {res.stderr.strip()}")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="StokScan AI Local Supabase Backup Tool")
    parser.add_argument("--mode", choices=["full", "core"], default="full", help="Backup mode: full (all 57 tables) or core (user/business tables only)")
    parser.add_argument("--output-dir", type=str, default=None, help="Custom output directory")
    parser.add_argument("--mcp-dir", type=str, default=None, help="Optional directory containing MCP SQL snapshots for schema/auth")
    args = parser.parse_args()

    env_vals = {
        **dotenv.dotenv_values(ROOT_DIR / ".env"),
        **dotenv.dotenv_values(ROOT_DIR / "web" / ".env.local"),
        **os.environ,
    }
    supabase_url = env_vals.get("SUPABASE_URL") or env_vals.get("NEXT_PUBLIC_SUPABASE_URL")
    service_key = env_vals.get("SUPABASE_SERVICE_ROLE_KEY")
    db_url = env_vals.get("SUPABASE_DB_URL") or env_vals.get("DATABASE_URL")

    if not supabase_url or not service_key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env", file=sys.stderr)
        return 1

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    out_dir = Path(args.output_dir) if args.output_dir else (BACKUPS_ROOT / f"supabase_{args.mode}_{timestamp}")
    tables_dir = out_dir / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    print(f"============================================================")
    print(f"StokScan AI — Local Supabase Backup ({args.mode.upper()} MODE)")
    print(f"Target directory: {out_dir}")
    print(f"============================================================")

    # Optional native pg_dump if DB password URL & pg_dump binary exist
    if db_url:
        try_native_pg_dump(db_url, out_dir)

    # Load schema DDL & column types from MCP snapshot if provided, or existing schema snapshot in backups/
    schema_ddl: Dict[str, str] = {}
    functions_sql = ""
    col_types_by_table: Dict[str, Dict[str, str]] = {}
    auth_users_rows: List[Dict[str, Any]] = []
    auth_identities_rows: List[Dict[str, Any]] = []

    if args.mcp_dir:
        mcp_path = Path(args.mcp_dir)
        s63 = extract_mcp_json(mcp_path / "63" / "output.txt")
        if s63 and len(s63) > 0:
            schema_ddl = s63[0]
        s65 = extract_mcp_json(mcp_path / "65" / "output.txt")
        if s65 and len(s65) > 0:
            functions_sql = s65[0].get("functions_sql", "")
        s77 = extract_mcp_json(mcp_path / "77" / "output.txt")
        if s77:
            for item in s77:
                col_types_by_table.setdefault(item["table_name"], {})[item["column_name"]] = item["data_type"]
        s72 = extract_mcp_json(mcp_path / "72" / "output.txt")
        if s72 and len(s72) > 0 and s72[0].get("users_data"):
            auth_users_rows = s72[0]["users_data"]
        s73 = extract_mcp_json(mcp_path / "73" / "output.txt")
        if s73 and len(s73) > 0 and s73[0].get("identities_data"):
            auth_identities_rows = s73[0]["identities_data"]

    # Cache schema snapshot inside backups/latest_schema_snapshot.json so future runs without MCP still have full DDL
    schema_cache_file = BACKUPS_ROOT / "latest_schema_snapshot.json"
    if schema_ddl:
        schema_cache_file.write_text(
            json.dumps(
                {
                    "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "schema_ddl": schema_ddl,
                    "functions_sql": functions_sql,
                    "col_types_by_table": col_types_by_table,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    elif schema_cache_file.exists():
        cached = json.loads(schema_cache_file.read_text(encoding="utf-8"))
        schema_ddl = cached.get("schema_ddl", {})
        functions_sql = cached.get("functions_sql", "")
        col_types_by_table = cached.get("col_types_by_table", {})

    if not auth_users_rows:
        print("[backup] Fetching auth.users via Supabase Auth Admin API...")
        auth_users_rows = fetch_auth_users_admin_api(supabase_url, service_key)

    sql_path = out_dir / "full_backup.sql"
    manifest_tables: Dict[str, Any] = {}
    total_rows_exported = 0
    start_time = time.time()

    tables_to_export = (
        {k: PUBLIC_TABLES_PK[k] for k in CORE_TABLES_ONLY if k in PUBLIC_TABLES_PK}
        if args.mode == "core"
        else PUBLIC_TABLES_PK
    )

    with sql_path.open("w", encoding="utf-8", newline="\n") as sql_fp:
        sql_fp.write("-- ============================================================================\n")
        sql_fp.write("-- StokScan AI — Complete PostgreSQL / Supabase Backup Dump\n")
        sql_fp.write(f"-- Project ID: gfcmaxbtscmizsakarvc (eu-west-1, PostgreSQL 17)\n")
        sql_fp.write(f"-- Generated At (UTC): {dt.datetime.now(dt.timezone.utc).isoformat()}\n")
        sql_fp.write(f"-- Mode: {args.mode.upper()}\n")
        sql_fp.write("-- ============================================================================\n\n")
        sql_fp.write("SET statement_timeout = 0;\n")
        sql_fp.write("SET lock_timeout = 0;\n")
        sql_fp.write("SET client_encoding = 'UTF8';\n")
        sql_fp.write("SET standard_conforming_strings = on;\n")
        sql_fp.write("SET check_function_bodies = false;\n")
        sql_fp.write("SET session_replication_role = 'replica';\n\n")

        if schema_ddl:
            sql_fp.write("-- ============================================================================\n")
            sql_fp.write("-- 1. ENUMS & SEQUENCES\n")
            sql_fp.write("-- ============================================================================\n\n")
            if schema_ddl.get("enums_sql"):
                sql_fp.write(schema_ddl["enums_sql"] + "\n\n")
            if schema_ddl.get("seqs_sql"):
                sql_fp.write(schema_ddl["seqs_sql"] + "\n\n")

            sql_fp.write("-- ============================================================================\n")
            sql_fp.write("-- 2. PUBLIC TABLES (DDL)\n")
            sql_fp.write("-- ============================================================================\n\n")
            sql_fp.write(schema_ddl.get("tables_sql", "") + "\n\n")

        # Write Auth data first
        sql_fp.write("-- ============================================================================\n")
        sql_fp.write("-- 3. AUTH SCHEMA DATA (auth.users & auth.identities)\n")
        sql_fp.write("-- ============================================================================\n\n")

        if auth_users_rows:
            auth_users_jsonl = tables_dir / "auth.users.jsonl.gz"
            with gzip.open(auth_users_jsonl, "wt", encoding="utf-8") as gz:
                for r in auth_users_rows:
                    gz.write(json.dumps(r, ensure_ascii=False) + "\n")
            write_sql_inserts_for_table(
                sql_fp,
                "auth",
                "users",
                auth_users_rows,
                {"raw_app_meta_data": "jsonb", "raw_user_meta_data": "jsonb"},
                batch_size=100,
            )
            manifest_tables["auth.users"] = {"rows": len(auth_users_rows), "file": "tables/auth.users.jsonl.gz"}
            total_rows_exported += len(auth_users_rows)
            print(f"  [OK] auth.users: {len(auth_users_rows)} rows")

        if auth_identities_rows:
            auth_ident_jsonl = tables_dir / "auth.identities.jsonl.gz"
            with gzip.open(auth_ident_jsonl, "wt", encoding="utf-8") as gz:
                for r in auth_identities_rows:
                    gz.write(json.dumps(r, ensure_ascii=False) + "\n")
            write_sql_inserts_for_table(
                sql_fp,
                "auth",
                "identities",
                auth_identities_rows,
                {"identity_data": "jsonb"},
                batch_size=100,
            )
            manifest_tables["auth.identities"] = {"rows": len(auth_identities_rows), "file": "tables/auth.identities.jsonl.gz"}
            total_rows_exported += len(auth_identities_rows)
            print(f"  [OK] auth.identities: {len(auth_identities_rows)} rows")

        sql_fp.write("-- ============================================================================\n")
        sql_fp.write("-- 4. PUBLIC SCHEMA TABLE DATA\n")
        sql_fp.write("-- ============================================================================\n\n")

        for idx, (table_name, pk_cols) in enumerate(tables_to_export.items(), 1):
            t0 = time.time()
            rows = fetch_rest_table(supabase_url, service_key, table_name, pk_cols)
            elapsed = time.time() - t0

            jsonl_file = tables_dir / f"public.{table_name}.jsonl.gz"
            with gzip.open(jsonl_file, "wt", encoding="utf-8") as gz:
                for r in rows:
                    gz.write(json.dumps(r, ensure_ascii=False) + "\n")

            t_col_types = col_types_by_table.get(table_name, {})
            # High-row tables use larger batch size for compact SQL
            b_size = 500 if len(rows) > 5000 else 200
            write_sql_inserts_for_table(sql_fp, "public", table_name, rows, t_col_types, batch_size=b_size)

            manifest_tables[f"public.{table_name}"] = {
                "rows": len(rows),
                "pk": pk_cols,
                "file": f"tables/public.{table_name}.jsonl.gz",
                "elapsed_sec": round(elapsed, 2),
            }
            total_rows_exported += len(rows)
            print(f"  [{idx:02d}/{len(tables_to_export):02d}] public.{table_name}: {len(rows):,} rows ({elapsed:.1f}s)")

        if schema_ddl or functions_sql:
            sql_fp.write("-- ============================================================================\n")
            sql_fp.write("-- 5. CONSTRAINTS, INDEXES, FUNCTIONS, VIEWS, TRIGGERS & RLS POLICIES\n")
            sql_fp.write("-- ============================================================================\n\n")
            if schema_ddl.get("constraints_sql"):
                sql_fp.write("-- Constraints\n" + schema_ddl["constraints_sql"] + "\n\n")
            if schema_ddl.get("indexes_sql"):
                sql_fp.write("-- Indexes\n" + schema_ddl["indexes_sql"] + "\n\n")
            if functions_sql:
                sql_fp.write("-- Functions\n" + functions_sql + "\n\n")
            if schema_ddl.get("views_sql"):
                sql_fp.write("-- Views\n" + schema_ddl["views_sql"] + "\n\n")
            if schema_ddl.get("triggers_sql"):
                sql_fp.write("-- Triggers\n" + schema_ddl["triggers_sql"] + "\n\n")
            if schema_ddl.get("policies_sql"):
                sql_fp.write("-- RLS Policies\n" + schema_ddl["policies_sql"] + "\n\n")

        sql_fp.write("SET session_replication_role = 'origin';\n")
        sql_fp.write("-- End of StokScan AI Supabase Backup Dump\n")

    # Compress full_backup.sql -> full_backup.sql.gz
    sql_gz_path = out_dir / "full_backup.sql.gz"
    with sql_path.open("rb") as f_in, gzip.open(sql_gz_path, "wb", compresslevel=6) as f_out:
        shutil.copyfileobj(f_in, f_out)

    sql_size_mb = round(sql_path.stat().st_size / (1024 * 1024), 2)
    gz_size_mb = round(sql_gz_path.stat().st_size / (1024 * 1024), 2)
    sql_sha256 = compute_sha256(sql_path)
    gz_sha256 = compute_sha256(sql_gz_path)

    manifest = {
        "project_id": "gfcmaxbtscmizsakarvc",
        "project_name": "ai scanner",
        "region": "eu-west-1",
        "postgres_version": "17.6.1.063",
        "backup_mode": args.mode,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_tables_exported": len(manifest_tables),
        "total_rows_exported": total_rows_exported,
        "elapsed_seconds": round(time.time() - start_time, 2),
        "artifacts": {
            "full_sql": {
                "path": "full_backup.sql",
                "size_mb": sql_size_mb,
                "sha256": sql_sha256,
            },
            "full_sql_gzip": {
                "path": "full_backup.sql.gz",
                "size_mb": gz_size_mb,
                "sha256": gz_sha256,
            },
        },
        "storage_buckets": [
            {"id": "ai-models", "public": True},
            {"id": "old-stock-data", "public": False},
            {"id": "chat-images", "public": True},
            {"id": "social-reports", "public": True, "file_size_limit": 5242880, "allowed_mime_types": ["image/png"]},
        ],
        "tables": manifest_tables,
    }

    manifest_path = out_dir / "backup_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Also update a pointer file in backups/latest_backup.json
    (BACKUPS_ROOT / "latest_backup.json").write_text(
        json.dumps(
            {
                "latest_backup_dir": str(out_dir.relative_to(ROOT_DIR)),
                "created_at_utc": manifest["created_at_utc"],
                "total_tables_exported": manifest["total_tables_exported"],
                "total_rows_exported": manifest["total_rows_exported"],
                "full_sql_size_mb": sql_size_mb,
                "full_sql_gz_size_mb": gz_size_mb,
                "full_sql_sha256": sql_sha256,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"============================================================")
    print(f"BACKUP COMPLETED SUCCESSFULLY!")
    print(f"Total Tables: {len(manifest_tables)} | Total Rows: {total_rows_exported:,}")
    print(f"SQL Dump:     {sql_path} ({sql_size_mb} MB)")
    print(f"Compressed:   {sql_gz_path} ({gz_size_mb} MB)")
    print(f"Manifest:     {manifest_path}")
    print(f"============================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
