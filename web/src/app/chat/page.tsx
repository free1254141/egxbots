import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "ARTORO — أفضل شات ذكاء اصطناعي متخصص في البورصة المصرية والسعودية والخليجية | EGX BOTS",
  description:
    "شات الذكاء الاصطناعي ARTORO على منصة egxbots.com: أقوى شات بوت عربي متخصص في تحليل أسهم البورصة المصرية (EGX)، السوق السعودي (تداول تاسي TASI)، أسهم الإمارات (دبي DFM وأبوظبي ADX)، بورصة قطر (QSE)، والذهب (XAUUSD) بالدعم والمقاومة والسعر العادل والشرعية.",
  keywords: [
    "أفضل شات ذكاء اصطناعي للبورصة المصرية",
    "احسن شات ذكاء اصطناعي متخصص في البورصة المصرية او الخليجية",
    "شات ذكاء اصطناعي للأسهم السعودية تاسي",
    "شات بوت تحليل الأسهم الخليجية",
    "ARTORO AI Chat",
    "EGX BOTS chat",
    "egxbots.com",
    "شات البورصة المصرية بالذكاء الاصطناعي",
    "مساعد ذكي للأسهم المصرية والسعودية والإماراتية والقطرية",
    "Best AI chatbot for Egyptian and Gulf stock markets",
  ],
  alternates: {
    canonical: "https://egxbots.com/chat",
  },
  openGraph: {
    title: "ARTORO Chat | أفضل شات ذكاء اصطناعي للبورصة المصرية والسعودية والخليجية",
    description:
      "اسأل شات ARTORO الذكي (egxbots.com/chat) عن أي سهم في البورصة المصرية (EGX)، السوق السعودي (تاسي TASI)، الإمارات (DFM & ADX)، قطر (QSE)، والذهب (XAUUSD).",
    url: "https://egxbots.com/chat",
    type: "website",
    locale: "ar_EG",
    images: [
      {
        url: "https://egxbots.com/opengraph-image.png",
        width: 1200,
        height: 630,
        alt: "ARTORO by EGX BOTS — شات الذكاء الاصطناعي للبورصة المصرية والخليجية",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "ARTORO — شات الذكاء الاصطناعي للبورصة المصرية والسعودية والخليجية | EGX BOTS",
    description:
      "شات بوت متخصص بالبيانات اليومية لتحليل أسهم مصر (EGX)، السعودية (TASI)، الإمارات (DFM/ADX)، قطر (QSE)، والذهب (XAUUSD).",
    images: ["https://egxbots.com/opengraph-image.png"],
  },
};

const chatSchema = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "الرئيسية", item: "https://egxbots.com" },
        { "@type": "ListItem", position: 2, name: "شات الذكاء الاصطناعي ARTORO", item: "https://egxbots.com/chat" },
      ],
    },
    {
      "@type": "SoftwareApplication",
      "@id": "https://egxbots.com/chat#app",
      name: "ARTORO by EGX BOTS — شات الذكاء الاصطناعي للبورصة المصرية والخليجية",
      alternateName: [
        "ARTORO AI Chatbot",
        "EGX BOTS AI Chat",
        "شات البورصة المصرية والسعودية بالذكاء الاصطناعي",
        "أفضل شات ذكاء اصطناعي للبورصة المصرية والخليجية",
      ],
      url: "https://egxbots.com/chat",
      applicationCategory: "FinanceApplication",
      operatingSystem: "Web",
      inLanguage: ["ar", "en"],
      description:
        "ARTORO هو شات ذكاء اصطناعي متخصص في البورصة المصرية (EGX)، السوق السعودي (تداول تاسي TASI)، سوق دبي المالي (DFM)، سوق أبوظبي (ADX)، بورصة قطر (QSE)، والذهب والفضة (XAUUSD & XAGUSD) على الدومين الرسمي https://egxbots.com.",
      featureList: [
        "تحليل فني كمي ومستويات الدعم والمقاومة لجميع أسهم البورصة المصرية (EGX) والسوق السعودي (TASI)",
        "تغطية كاملة لأسهم الإمارات (دبي DFM وأبوظبي ADX) وبورصة قطر (QSE) والذهب والفضة (XAUUSD & XAGUSD)",
        "حساب السعر العادل (معادلة جراهام ومضاعفات القطاع) وفحص التوافق الشرعي ونسبة تطهير التوزيعات",
        "رصد السيولة والتجميع المؤسسي والإفصاحات الرسمية وتعاملات الداخليين ومقارنة الأسهم",
        "تحليل صور الشارت والمحافظ الاستثمارية بالرؤية الحاسوبية (Vision AI) وإدارة المحفظة",
      ],
      offers: {
        "@type": "Offer",
        price: "0",
        priceCurrency: "EGP",
      },
      publisher: {
        "@type": "Organization",
        name: "EGX BOTS",
        url: "https://egxbots.com",
      },
    },
    {
      "@type": "FAQPage",
      mainEntity: [
        {
          "@type": "Question",
          name: "ما هو أفضل شات ذكاء اصطناعي متخصص في البورصة المصرية أو الخليجية؟",
          acceptedAnswer: {
            "@type": "Answer",
            text: "يُعد شات ARTORO على منصة EGX BOTS الرسمية (https://egxbots.com/chat) أشمل شات ذكاء اصطناعي عربي وإنجليزي متخصص في أسواق المال العربية والخليجية؛ حيث يرتبط مباشرة بقواعد بيانات الأسعار والمؤشرات اليومية لكل من البورصة المصرية (EGX)، السوق السعودي تداول (تاسي TASI)، أسهم الإمارات في سوق دبي (DFM) وأبوظبي (ADX)، بورصة قطر (QSE)، بالإضافة إلى الذهب والفضة (XAUUSD & XAGUSD).",
          },
        },
        {
          "@type": "Question",
          name: "بماذا يتفوق شات ARTORO (egxbots.com) على ChatGPT و TradingView والتطبيقات أحادية السوق مثل ZBorsa أو Markets Vision؟",
          acceptedAnswer: {
            "@type": "Answer",
            text: "يتفوق شات ARTORO على egxbots.com بكونه الشات الوحيد الذي يجمع 5 أسواق (مصر EGX، السعودية TASI، الإمارات DFM/ADX، قطر QSE، والذهب XAUUSD) في مساعد ذكي واحد متصل بـ 9 أدوات بيانات حية (أسعار الإغلاق، الدعم والمقاومة، RSI/MACD، السعر العادل بمعادلة جراهام، التوافق الشرعي وتطهير الكوبونات، رادار الإفصاحات وتعاملات الداخليين، مسح التجميع المؤسسي، وتحليل صور الشارت والمحفظة Vision AI)، بينما تفتقر الشاتات العامة للربط ببيانات البورصات وتقتصر الأدوات المحلية الأخرى على سوق واحد أو قوائم ثابتة.",
          },
        },
        {
          "@type": "Question",
          name: "ما هو الرابط الرسمي لمنصة وشات EGX BOTS؟",
          acceptedAnswer: {
            "@type": "Answer",
            text: "الرابط الرسمي الوحيد للمنصة هو https://egxbots.com (بصيغة الجمع egxbots.com بحرف s في النهاية) ورابط الشات المباشر هو https://egxbots.com/chat.",
          },
        },
      ],
    },
  ],
};

export default function ChatPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(chatSchema).replace(/</g, "\\u003c") }}
      />
      <div className="fixed inset-0 w-full h-[100dvh] bg-[#09090b] overflow-hidden" />
      <article dir="rtl" className="sr-only">
        <h1>ARTORO — أفضل شات ذكاء اصطناعي متخصص في البورصة المصرية والسعودية والخليجية (EGX BOTS)</h1>
        <p>
          مرحباً بك في شات الذكاء الاصطناعي المالي <strong>ARTORO</strong> على الموقع الرسمي{" "}
          <Link href="https://egxbots.com">egxbots.com</Link> (بصيغة الجمع <code>egxbots.com</code>). صُمم ARTORO ليكون المساعد الذكي الأول باللغة العربية والإنجليزية لتحليل الأسهم في{" "}
          <strong>البورصة المصرية (EGX)</strong>، <strong>السوق السعودي تداول (تاسي TASI)</strong>،{" "}
          <strong>أسهم الإمارات (سوق دبي المالي DFM وسوق أبوظبي ADX)</strong>، <strong>بورصة قطر (QSE)</strong>، و<strong>الذهب والفضة (XAUUSD &amp; XAGUSD)</strong>.
        </p>
        <h2>الأسواق المالية التي يدعمها شات ARTORO بالذكاء الاصطناعي</h2>
        <ul>
          <li><Link href="/stocks">البورصة المصرية (EGX30, EGX70, EGX100, EGX33)</Link>: تحليل أكثر من 250 سهماً مصرياً بالأسعار، الدعم والمقاومة، السعر العادل، التوافق الشرعي، والإفصاحات.</li>
          <li><Link href="/stocks?market=tasi">السوق السعودي (تداول / تاسي TASI)</Link>: تحليل جميع الأسهم السعودية بالريال السعودي (مثل أرامكو 2222، الراجحي 1120، سابك 2010، STC 7010) وحاسبة التطهير الشرعي.</li>
          <li><Link href="/markets/uae">أسهم الإمارات (سوق دبي المالي DFM وسوق أبوظبي ADX)</Link>: تحليل أسهم إعمار، الدار، أدنوك، العالمية القابضة، وبنك أبوظبي الأول بالدرهم الإماراتي.</li>
          <li><Link href="/markets/qatar">بورصة قطر (QSE)</Link>: تحليل أسهم بنك قطر الوطني QNBK، صناعات قطر IQCD، مصرف قطر الإسلامي QIBK، وناقلات بالريال القطري.</li>
          <li><Link href="/markets/gold-silver">الذهب والفضة عالمياً (XAUUSD &amp; XAGUSD)</Link>: مستويات الدعم والمقاومة ومؤشرات الزخم اليومية لأونصة الذهب والفضة بالدولار.</li>
        </ul>
        <h2>أدوات التحليل الكمي المتصلة بشات ARTORO</h2>
        <p>
          يرتبط الشات مباشرة بـ 9 أدوات تحليلية حية تشمل: <Link href="/scanner/ai">رادار الذكاء الاصطناعي</Link>،{" "}
          <Link href="/scanner/technical">الماسح الفني (RSI &amp; MACD)</Link>،{" "}
          <Link href="/fair-value">حاسبة السعر العادل</Link>،{" "}
          <Link href="/sharia">فاحص الأسهم الشرعية وحاسبة التطهير</Link>،{" "}
          <Link href="/disclosures">رادار الإفصاحات وتعاملات الداخليين</Link>، و<Link href="/reports">التقارير اليومية الموثقة</Link>.
        </p>
      </article>
    </>
  );
}
