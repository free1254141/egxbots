import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

desktop = r'C:\Users\MR__CODER__\Desktop'

def load_csv(name):
    p = os.path.join(desktop, name)
    for enc in ['utf-8', 'utf-8-sig', 'cp1256']:
        try:
            return pd.read_csv(p, encoding=enc)
        except Exception:
            pass
    return None

filters_df = load_csv('الفلاتر.csv')
devices_df = load_csv('الأجهزة.csv')
countries_df = load_csv('البلدان.csv')
pages_df = load_csv('الصفحات.csv')
queries_df = load_csv('طلبات البحث.csv')
chart_df = load_csv('رسم بياني.csv')
appearance_df = load_csv('شكل الظهور في البحث.csv')

print("=== 1. الفلاتر ===")
if filters_df is not None:
    print(filters_df.to_string())

print("\n=== 2. الأجهزة (Devices) ===")
if devices_df is not None:
    print(devices_df.to_string())

print("\n=== 3. البلدان (Countries) ===")
if countries_df is not None:
    print(countries_df.to_string())

print("\n=== 4. الصفحات (Pages) ===")
if pages_df is not None:
    print(pages_df.to_string())

print("\n=== 5. شكل الظهور ===")
if appearance_df is not None:
    print(appearance_df.to_string())

print("\n=== 6. ملخص الرسم البياني (Daily Trend) ===")
if chart_df is not None:
    print(f"عدد الأيام: {len(chart_df)}")
    print(f"أول تاريخ: {chart_df.iloc[0, 0]} | آخر تاريخ: {chart_df.iloc[-1, 0]}")
    print(chart_df.tail(10).to_string())

print("\n=== 7. الكلمات التي حصلت على نقرات (Clicks > 0) ===")
if queries_df is not None:
    clicks_col = queries_df.columns[1]
    imp_col = queries_df.columns[2]
    ctr_col = queries_df.columns[3]
    pos_col = queries_df.columns[4]
    q_col = queries_df.columns[0]
    
    with_clicks = queries_df[queries_df[clicks_col] > 0]
    print(with_clicks.to_string())

    print("\n=== 8. الكلمات في الصفحة الأولى (Position <= 10) ===")
    top10 = queries_df[queries_df[pos_col] <= 10].sort_values(by=imp_col, ascending=False)
    print(f"عددها: {len(top10)}")
    print(top10.to_string())
