"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

export default function MobileConversation({ open, onClose, title, closeLabel, className, testId, children }: {
    open: boolean;
    onClose: () => void;
    title: string;
    closeLabel: string;
    className: string;
    testId: string;
    children: ReactNode;
}) {
    const [mobile, setMobile] = useState(false);
    const returnFocus = useRef<HTMLElement | null>(null);

    useEffect(() => {
        const media = window.matchMedia("(max-width: 767px)");
        const update = () => setMobile(media.matches);
        update();
        media.addEventListener("change", update);
        return () => media.removeEventListener("change", update);
    }, []);

    if (!mobile) {
        return <div data-testid={testId} className={`hidden md:flex ${className}`}>{children}</div>;
    }

    return (
        <Dialog.Root open={open} onOpenChange={(value) => { if (!value) onClose(); }}>
            <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 z-[100000] bg-black/60" />
                <Dialog.Content
                    data-testid={testId}
                    aria-describedby={undefined}
                    className="fixed inset-2 z-[100001] h-[calc(100dvh-1rem)] min-h-0 min-w-0 flex flex-col overflow-hidden rounded-xl border-2 border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-black dark:text-white shadow-xl"
                    onOpenAutoFocus={() => { returnFocus.current = document.activeElement as HTMLElement; }}
                    onCloseAutoFocus={(event) => { event.preventDefault(); returnFocus.current?.focus(); }}
                >
                    <div className="flex min-h-12 shrink-0 items-center justify-between gap-2 border-b border-zinc-200 dark:border-zinc-800 px-3">
                        <Dialog.Title className="min-w-0 truncate text-sm font-bold">{title}</Dialog.Title>
                        <Dialog.Close aria-label={closeLabel} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800">
                            <X className="h-5 w-5" />
                        </Dialog.Close>
                    </div>
                    <div className="flex flex-1 min-h-0 min-w-0 flex-col overflow-hidden">{children}</div>
                </Dialog.Content>
            </Dialog.Portal>
        </Dialog.Root>
    );
}
