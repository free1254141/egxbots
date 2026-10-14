import type { Metadata } from "next";

export const metadata: Metadata = {
    title: "ARTORO — شات الذكاء الاصطناعي للبورصة المصرية | EGX BOTS",
    description: "مساعد البورصة المصرية بالذكاء الاصطناعي ARTORO: تحليل الأسهم، إشارات وتوقعات النماذج الفنية، ومتابعة السيولة والتجميع.",
    alternates: {
        canonical: "https://egxbots.com/chat",
    },
    openGraph: {
        title: "ARTORO Chat | شات البورصة المصرية بالذكاء الاصطناعي",
        description: "مساعد البورصة المصرية بالذكاء الاصطناعي ARTORO: تحليل فني لحظي، إشارات ذكاء اصطناعي، ومتابعة السيولة.",
        url: "https://egxbots.com/chat",
        type: "website",
        locale: "ar_EG",
    },
};

export default function ChatPage() {
    return (
        <div className="fixed inset-0 w-full h-[100dvh] bg-[#09090b] overflow-hidden" />
    );
}
