import type { Metadata } from "next";
import AffiliateClient from "./AffiliateClient";

export const metadata: Metadata = {
  title: "اربح 25% عمولة كاش متكررة | برنامج شركاء EGX BOTS للبورصة",
  description:
    "احصل على رابط الإحالة وكود الخصم الخاص بك في منصة EGX BOTS لتحليل أسهم البورصة المصرية والسعودية، وامنح أصدقاءك خصم 10% واربح 25% عمولة كاش عبر فودافون كاش أو إنستاباي أو STC Pay.",
  alternates: {
    canonical: "https://egxbots.com/affiliate",
  },
  openGraph: {
    title: "اربح 25% عمولة كاش | برنامج شركاء النجاح EGX BOTS",
    description:
      "شارك رابط الإحالة وكود الخصم الخاص بك: خصم 10% لأصدقائك و25% عمولة كاش لك على كل اشتراك مكتمل عبر فودافون كاش أو إنستاباي أو STC Pay.",
    url: "https://egxbots.com/affiliate",
    type: "website",
    images: [
      {
        url: "https://egxbots.com/opengraph-image.png",
        width: 1200,
        height: 630,
        alt: "برنامج شركاء النجاح والتسويق بالعمولة EGX BOTS",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "اربح 25% عمولة كاش | برنامج شركاء EGX BOTS",
    description:
      "امنح أصدقاءك خصم 10% على باقات EGX BOTS واربح 25% عمولة كاش عبر فودافون كاش أو إنستاباي أو STC Pay.",
    images: ["https://egxbots.com/opengraph-image.png"],
  },
};

const affiliateSchema = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "الرئيسية", item: "https://egxbots.com" },
        { "@type": "ListItem", position: 2, name: "برنامج التسويق بالعمولة", item: "https://egxbots.com/affiliate" },
      ],
    },
    {
      "@type": "WebPage",
      "@id": "https://egxbots.com/affiliate#webpage",
      name: "برنامج التسويق بالعمولة وشركاء النجاح | EGX BOTS",
      url: "https://egxbots.com/affiliate",
      description:
        "برنامج شركاء EGX BOTS يتيح لك ربح 25% عمولة كاش على كل اشتراك مدفوع مع خصم 10% للمشتركين عبر رابطك أو كودك.",
      publisher: { "@type": "Organization", name: "EGX BOTS", url: "https://egxbots.com" },
    },
    {
      "@type": "FAQPage",
      mainEntity: [
        {
          "@type": "Question",
          name: "كم تبلغ نسبة العمولة في برنامج شركاء EGX BOTS؟",
          acceptedAnswer: {
            "@type": "Answer",
            text: "تحصل على عمولة نقدية بنسبة 25% على كل اشتراك مدفوع يتم عبر رابط الإحالة أو كود الخصم الخاص بك، كما يحصل المشترك على خصم فوري 10%.",
          },
        },
        {
          "@type": "Question",
          name: "ما هي طرق سحب أرباح التسويق بالعمولة؟",
          acceptedAnswer: {
            "@type": "Answer",
            text: "يمكنك استلام أرباحك عبر المحافظ الإلكترونية (فودافون كاش / اتصالات / أورنج / WE)، أو إنستاباي، أو STC Pay، أو التحويل البنكي.",
          },
        },
      ],
    },
  ],
};

export default function AffiliatePage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(affiliateSchema).replace(/</g, "\\u003c") }}
      />
      <AffiliateClient />
    </>
  );
}
