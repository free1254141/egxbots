'use client';

import Link from 'next/link';
import BrandedPageHeader from '@/components/BrandedPageHeader';
import { useLanguage } from '@/contexts/LanguageContext';

// Imported normally by the server page: visible HTML before the dynamic scanner
// loads, and the same content remains visible when language/hydration changes.
export default function TechnicalScannerGuide() {
    const { language } = useLanguage();
    const ar = language === 'ar';
    return <section dir={ar ? 'rtl' : 'ltr'} className="app-page-shell pt-5 sm:pt-7">
        <BrandedPageHeader compact dir={ar ? 'rtl' : 'ltr'}
            eyebrow={ar ? 'فحص وتحليل الأسهم' : 'EGX STOCK SCREENER'}
            title={ar ? 'الماسح الفني للأسهم المصرية' : 'Egyptian stock technical scanner'}
            description={ar
                ? 'افحص أسهم البورصة المصرية بمؤشرات RSI وMACD والمتوسطات المتحركة والحجم. اختر الفلاتر للمقارنة بين الأسهم وفق آخر بيانات محفوظة، وليست أسعاراً لحظية.'
                : 'Screen EGX stocks using RSI, MACD, moving averages and volume. Compare stocks with your chosen filters using saved market data, not live quotes.'} />
        <div className="mb-5 grid gap-4 border border-zinc-200 bg-white p-4 text-sm leading-7 text-zinc-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 sm:grid-cols-2 sm:p-5">
            <div><h2 className="font-bold text-zinc-950 dark:text-white">{ar ? 'طريقة الاستخدام' : 'How to use the scanner'}</h2>
                <p>{ar ? 'ابدأ بأحد قوالب الفحص أو عدّل مرشحات المؤشرات والسيولة. شغّل الفحص، ثم رتّب النتائج وافتح السهم أو المقارنة لمراجعة التفاصيل.'
                    : 'Start with a screening template or adjust indicator and liquidity filters. Run the scan, sort the results, then open a stock or comparison to review the details.'}</p></div>
            <div><h2 className="font-bold text-zinc-950 dark:text-white">{ar ? 'تاريخ البيانات وحدودها' : 'Data dates and limits'}</h2>
                <p>{ar ? 'راجع تاريخ التحديث الظاهر في النتائج. اختلاف تواريخ البيانات يحدّ من المقارنة، والتشبع البيعي أو إشارة المؤشر وحدهما لا يثبتان فرصة شراء أو أرباحاً مستقبلية.'
                    : 'Check the update date shown with the results. Different snapshot dates limit comparisons. Oversold readings or an indicator signal alone do not establish a buying opportunity or future returns.'}</p></div>
        </div>
        <nav aria-label={ar ? 'أدلة وأدوات التحليل' : 'Market guides and analysis tools'} className="mb-5 flex flex-wrap gap-x-5 gap-y-2 text-sm font-medium text-amber-700 dark:text-amber-300">
            {[['/stocks', ar ? 'دليل الأسهم' : 'Stock directory'], ['/reports', ar ? 'التقارير اليومية' : 'Daily reports'],
                ['/scanner/comparison', ar ? 'مقارنة الأسهم' : 'Stock comparison'], ['/scanner/backtests', ar ? 'التشابه التاريخي' : 'Historical similarity']]
                .map(([href, label]) => <Link key={href} href={href} className="underline underline-offset-4 hover:text-amber-500">{label}</Link>)}
        </nav>
    </section>;
}
