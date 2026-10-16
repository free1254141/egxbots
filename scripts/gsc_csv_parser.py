"""
GSC CSV / Excel Export Parser for EGX Bots.
Parses Google Search Console exported ZIP or CSV files instantly.
"""

import os
import sys
import glob
import zipfile
import pandas as pd
from pathlib import Path

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

def find_latest_export():
    candidates = []
    # Check current dir, downloads, or scripts
    search_dirs = [
        '.',
        'scripts',
        str(Path.home() / 'Downloads'),
    ]
    for d in search_dirs:
        if os.path.exists(d):
            candidates.extend(glob.glob(os.path.join(d, '*egxbots*.zip')))
            candidates.extend(glob.glob(os.path.join(d, 'Performance*.zip')))
            candidates.extend(glob.glob(os.path.join(d, '*Search_Console*.zip')))
            candidates.extend(glob.glob(os.path.join(d, 'Queries.csv')))
            candidates.extend(glob.glob(os.path.join(d, '*Queries*.csv')))
    
    if not candidates:
        return None
    # Sort by modification time
    candidates.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return candidates[0]


def parse_export(file_path):
    print(f"\n📂 جاري قراءة الملف: {file_path}")
    queries_df = None
    pages_df = None
    countries_df = None

    if file_path.endswith('.zip'):
        with zipfile.ZipFile(file_path, 'r') as z:
            for filename in z.namelist():
                if 'Queries.csv' in filename:
                    with z.open(filename) as f:
                        queries_df = pd.read_csv(f)
                elif 'Pages.csv' in filename:
                    with z.open(filename) as f:
                        pages_df = pd.read_csv(f)
                elif 'Countries.csv' in filename:
                    with z.open(filename) as f:
                        countries_df = pd.read_csv(f)
    elif file_path.endswith('.csv'):
        queries_df = pd.read_csv(file_path)

    if queries_df is not None:
        # Standardize columns
        # GSC CSV usually has: Top queries, Clicks, Impressions, CTR, Position
        cols = {c: c.strip() for c in queries_df.columns}
        queries_df.rename(columns=cols, inplace=True)
        
        # Identify columns
        query_col = [c for c in queries_df.columns if 'quer' in c.lower() or 'بحث' in c or 'كلم' in c][0]
        clicks_col = [c for c in queries_df.columns if 'click' in c.lower() or 'نقرات' in c][0]
        impressions_col = [c for c in queries_df.columns if 'impress' in c.lower() or 'ظهور' in c][0]
        ctr_col = [c for c in queries_df.columns if 'ctr' in c.lower() or 'نسبة' in c][0]
        pos_col = [c for c in queries_df.columns if 'pos' in c.lower() or 'ترتيب' in c or 'موضع' in c][0]

        total_clicks = queries_df[clicks_col].sum()
        total_impressions = queries_df[impressions_col].sum()
        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        avg_pos = queries_df[pos_col].mean()

        print("\n" + "="*50)
        print("📊 ملخص الأداء الإجمالي (من ملف GSC)")
        print("="*50)
        print(f"🔹 إجمالي النقرات (Clicks): {total_clicks:,}")
        print(f"🔹 إجمالي الظهور (Impressions): {total_impressions:,}")
        print(f"🔹 متوسط نسبة النقر (CTR): {avg_ctr:.2f}%")
        print(f"🔹 متوسط الترتيب (Avg Position): {avg_pos:.1f}")
        print(f"🔹 عدد الكلمات المفهرسة: {len(queries_df):,}")

        print("\n🔥 أكثر الكلمات جلباً للنقرات (Top 10 by Clicks):")
        top_clicks = queries_df.sort_values(by=clicks_col, ascending=False).head(10)
        for _, r in top_clicks.iterrows():
            print(f"- {r[query_col]}: {r[clicks_col]} نقرة | {r[impressions_col]} ظهور | الترتيب: {r[pos_col]:.1f}")

        print("\n🎯 فرص ذهبية للقفز للصفحة الأولى (Striking Distance - ترتيب 5 إلى 20):")
        opportunities = queries_df[(queries_df[pos_col] >= 5.0) & (queries_df[pos_col] <= 20.0)].sort_values(by=impressions_col, ascending=False).head(10)
        if len(opportunities) == 0:
            print("لا توجد كلمات حالياً في هذا النطاق.")
        else:
            for _, r in opportunities.iterrows():
                print(f"⚡ {r[query_col]} -> ظهور: {r[impressions_col]} | نقرات: {r[clicks_col]} | الترتيب الحالي: {r[pos_col]:.1f}")

    if pages_df is not None:
        print("\n📄 أكثر الصفحات زيارة (Top Pages):")
        page_col = pages_df.columns[0]
        p_clicks = pages_df.columns[1]
        top_pages = pages_df.sort_values(by=p_clicks, ascending=False).head(5)
        for _, r in top_pages.iterrows():
            print(f"- {r[page_col]}: {r[p_clicks]} نقرة")

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else find_latest_export()
    if target and os.path.exists(target):
        parse_export(target)
    else:
        print("لم يتم العثور على ملف تصدير GSC. ضع الملف هنا وشغّل السكربت أو مرر مساره.")
