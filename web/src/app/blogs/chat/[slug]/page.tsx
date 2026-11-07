import { notFound } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const revalidate = 86400; // 24h ISR: caches on Edge CDN, zero Vercel Lambda CPU and zero Supabase reads

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
    const slug = (await params).slug;
    const post = await loadPost(slug);
    const title = post?.title ? `${post.title} | المدونة` : "تحليل سوق البورصة المصرية";
    const description = post?.question ? `سؤال وتحليل ذكي: ${post.question.slice(0, 150)}` : "تحليل سوق من EGX Bots";
    const url = `https://egxbots.com/blogs/chat/${slug}`;

    return {
        title,
        description,
        alternates: {
            canonical: url,
        },
        openGraph: {
            title,
            description,
            type: "article",
            url,
            publishedTime: post?.created_at,
            authors: ["EGX Bots AI"],
        },
        twitter: { card: "summary_large_image", title, description },
    };
}

async function loadPost(slug: string) {
    const supabase = await createSupabaseServerClient();
    const { data } = await supabase
        .from("shared_chat_posts")
        .select("slug, question, answer, title, created_at")
        .eq("slug", slug)
        .eq("is_published", true)
        .maybeSingle();
    return data;
}

export default async function SharedChatPage({ params }: { params: Promise<{ slug: string }> }) {
    const slug = (await params).slug;
    const post = await loadPost(slug);
    if (!post) notFound();

    const postUrl = `https://egxbots.com/blogs/chat/${slug}`;
    const articleSchema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "@id": `${postUrl}#article`,
        "headline": post.title,
        "description": post.question?.slice(0, 200),
        "datePublished": post.created_at,
        "dateModified": post.created_at,
        "mainEntityOfPage": postUrl,
        "author": {
            "@type": "Organization",
            "name": "EGX Bots AI"
        },
        "publisher": {
            "@type": "Organization",
            "name": "EGX BOTS",
            "logo": {
                "@type": "ImageObject",
                "url": "https://egxbots.com/favicon_io/android-chrome-512x512.png"
            }
        }
    };

    return (
        <main dir="rtl" className="min-h-screen bg-[#FFE600] dark:bg-zinc-950 px-4 py-10 text-black dark:text-zinc-100">
            <script
                type="application/ld+json"
                dangerouslySetInnerHTML={{ __html: JSON.stringify(articleSchema) }}
            />
            <article className="mx-auto max-w-4xl border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 shadow-[8px_8px_0_0_#000] dark:shadow-[8px_8px_0_0_#fff] sm:p-10">
                <div className="mb-8 border-b-4 border-black dark:border-white pb-5">
                    <p className="mb-3 font-mono text-xs font-black uppercase tracking-widest text-zinc-700 dark:text-zinc-300">EGX Bots Blog</p>
                    <h1 className="text-2xl font-black text-black dark:text-white sm:text-4xl">{post.title}</h1>
                    <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">{new Date(post.created_at).toLocaleDateString("ar-EG")}</p>
                </div>
                <section className="mb-8 border-2 border-black dark:border-cyan-500/60 bg-cyan-100 dark:bg-cyan-950/40 p-4 text-black dark:text-zinc-100">
                    <h2 className="mb-2 font-black">السؤال</h2>
                    <p className="whitespace-pre-wrap leading-8">{post.question}</p>
                </section>
                <section>
                    <h2 className="mb-3 text-xl font-black text-black dark:text-white">الإجابة</h2>
                    <div className="whitespace-pre-wrap leading-8 text-zinc-800 dark:text-zinc-200">{post.answer}</div>
                </section>
                <footer className="mt-10 border-t-4 border-black dark:border-white pt-4 text-xs text-zinc-600 dark:text-zinc-400">
                    تحليل آلي إحصائي مبني على البيانات المتاحة من EGX Bots لأغراض الدراسة والبحث فقط، وليس توصية استثمارية أو دعوة للشراء أو البيع.
                </footer>
            </article>
        </main>
    );
}
