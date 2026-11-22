import Link from 'next/link';
import type { Metadata } from 'next';
import BrandedPageHeader from '@/components/BrandedPageHeader';
import { getPublicReports, reportNames, reportUrl } from '@/lib/social/public-reports';
import { EgxOnlyGuard } from '@/contexts/MarketContext';

export const revalidate = 604800;
export const metadata: Metadata = {
  title: 'تقارير البورصة المصرية اليومية ورادار التجميع والسيولة | EGX BOTS',
  description: 'أرشيف تقارير EGX BOTS اليومية المؤرخة: وضع السوق (EGX30 & EGX100)، إشارات التجميع المؤسسي والسيولة، مع مصادر الأرقام ومنهجية التحليل.',
  alternates: { canonical: 'https://egxbots.com/reports' },
  openGraph: {
    title: 'تقارير البورصة المصرية اليومية ورادار التجميع والسيولة | EGX BOTS',
    description: 'تحليلات يومية مؤرخة لجلسات البورصة المصرية مع الأرقام المسجلة ومصادرها وإشارات التجميع عالية السيولة.',
    url: 'https://egxbots.com/reports',
    type: 'website',
    images: [{ url: 'https://egxbots.com/opengraph-image.png', width: 1200, height: 630, alt: 'تقارير البورصة المصرية اليومية EGX BOTS' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'تقارير البورصة المصرية اليومية ورادار التجميع | EGX BOTS',
    description: 'أرشيف تقارير الجلسات اليومية في البورصة المصرية ومؤشرات التجميع والسيولة بالذكاء الاصطناعي.',
    images: ['https://egxbots.com/opengraph-image.png'],
  },
};

export default async function ReportsPage() {
  const reports = await getPublicReports();
  const reportsSchema = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'BreadcrumbList',
        itemListElement: [
          { '@type': 'ListItem', position: 1, name: 'الرئيسية', item: 'https://egxbots.com' },
          { '@type': 'ListItem', position: 2, name: 'التقارير اليومية', item: 'https://egxbots.com/reports' },
        ],
      },
      {
        '@type': 'CollectionPage',
        '@id': 'https://egxbots.com/reports#webpage',
        name: 'تقارير البورصة المصرية اليومية ورادار التجميع والسيولة',
        url: 'https://egxbots.com/reports',
        description: 'أرشيف تقارير EGX BOTS المؤرخة لجلسات البورصة المصرية مع مصادر الأرقام ومنهجية التحليل.',
        mainEntity: {
          '@type': 'ItemList',
          numberOfItems: reports.length,
          itemListElement: reports.slice(0, 30).map((r, idx) => ({
            '@type': 'ListItem',
            position: idx + 1,
            name: `${reportNames[r.kind] || r.kind} — جلسة ${r.session_date}`,
            url: `https://egxbots.com${reportUrl(r)}`,
          })),
        },
      },
    ],
  };

  return (
    <EgxOnlyGuard sectionNameAr="تقارير السوق والتجميع" sectionNameEn="EGX Daily Market Reports">
      <main dir="rtl" className="mx-auto max-w-6xl px-4 py-8 text-zinc-950 dark:text-white">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(reportsSchema).replace(/</g, '\\u003c') }}
        />
        <BrandedPageHeader eyebrow="EGX BOTS RESEARCH" title="تقارير السوق والتجميع اليومية" description="تحليلات يومية مؤرخة من بيانات الجلسات المكتملة، مع الأرقام والمصادر وحدود التغطية." />
        <div className="grid gap-5 sm:grid-cols-2">
          {reports.map(r => <Link key={reportUrl(r)} href={reportUrl(r)} prefetch={false} className="border border-zinc-200 bg-white p-6 shadow-sm transition hover:border-amber-400 dark:border-slate-700 dark:bg-slate-900">
            <time dateTime={r.session_date} className="text-sm text-zinc-500 dark:text-slate-400">جلسة {r.session_date}</time>
            <h2 className="mt-3 text-xl font-bold">{reportNames[r.kind]}</h2>
            <p className="mt-3 text-sm leading-7 text-zinc-600 dark:text-slate-300">قراءة التقرير والأرقام المسجلة ومنهجية التحليل ←</p>
          </Link>)}
        </div>
        {!reports.length && <p className="py-12">لم تتوفر تقارير معتمدة للنشر بعد.</p>}
      </main>
    </EgxOnlyGuard>
  );
}
