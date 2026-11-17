import { notFound } from "next/navigation";
import { Metadata } from "next";
import { PILLAR_ARTICLES } from "@/lib/seo/pillar-articles";
import PillarArticleClient from "./PillarArticleClient";

export const revalidate = 604800;

export async function generateStaticParams() {
  return Object.keys(PILLAR_ARTICLES).map((slug) => ({ slug }));
}

interface PageProps {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const article = PILLAR_ARTICLES[slug];
  if (!article) return {};

  const url = `https://egxbots.com/blogs/${slug}`;
  const brandLabel = article.market === "tasi" ? "TASI BOTS" : "EGX BOTS";
  const title = `${article.title.ar} | ${brandLabel}`;
  const description = article.description.ar;

  return {
    title,
    description,
    keywords: article.keywords,
    alternates: {
      canonical: url,
    },
    openGraph: {
      title,
      description,
      url,
      type: "article",
      publishedTime: article.publishedAt,
      authors: [article.author.ar],
      images: [
        {
          url: "https://egxbots.com/opengraph-image.png",
          width: 1200,
          height: 630,
          alt: title,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: ["https://egxbots.com/opengraph-image.png"],
    },
  };
}

export default async function PillarArticlePage({ params }: PageProps) {
  const { slug } = await params;
  const article = PILLAR_ARTICLES[slug];
  if (!article) notFound();

  const articleUrl = `https://egxbots.com/blogs/${slug}`;

  const schemaGraph = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "BreadcrumbList",
        "itemListElement": [
          { "@type": "ListItem", "position": 1, "name": "الرئيسية", "item": "https://egxbots.com" },
          { "@type": "ListItem", "position": 2, "name": "المدونة", "item": "https://egxbots.com/blogs" },
          { "@type": "ListItem", "position": 3, "name": article.title.ar, "item": articleUrl },
        ],
      },
      {
        "@type": "Article",
        "@id": `${articleUrl}#article`,
        "headline": article.title.ar,
        "description": article.description.ar,
        "datePublished": article.publishedAt,
        "dateModified": article.publishedAt,
        "author": {
          "@type": "Organization",
          "name": article.author.ar,
          "url": "https://egxbots.com",
        },
        "publisher": {
          "@type": "Organization",
          "name": article.market === "tasi" ? "TASI BOTS" : "EGX BOTS",
          "logo": {
            "@type": "ImageObject",
            "url": "https://egxbots.com/icon-512.png",
          },
        },
        "mainEntityOfPage": articleUrl,
        "image": "https://egxbots.com/opengraph-image.png",
      },
      {
        "@type": "FAQPage",
        "mainEntity": article.faqs.map((faq) => ({
          "@type": "Question",
          "name": faq.question.ar,
          "acceptedAnswer": {
            "@type": "Answer",
            "text": faq.answer.ar,
          },
        })),
      },
    ],
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(schemaGraph).replace(/</g, "\\u003c") }}
      />
      <PillarArticleClient article={article} />
    </>
  );
}
