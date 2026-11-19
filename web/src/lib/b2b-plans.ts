export type B2BTierId = "b2b_starter" | "b2b_pro" | "b2b_enterprise";

export interface B2BTierSpec {
  id: B2BTierId;
  tag: string;
  name_ar: string;
  name_en: string;
  amount_egp: number;
  daily_limit: number;
  monthly_est: string;
  max_members_ar: string;
  max_members_en: string;
  groups_count: number;
  is_featured: boolean;
}

import { type CheckoutMarket, SAUDI_SAR_EXCHANGE_MAP, toDisplayAmount } from "@/lib/saudi-pricing";

export const B2B_SAR_EXCHANGE_MAP = SAUDI_SAR_EXCHANGE_MAP;

/** Convert an internal EGP price to the active market display currency (SAR/AED/QAR for Gulf, EGP for EGX). */
export function toB2BDisplayAmount(amountEgp: number, marketOrIsSaudi: boolean | CheckoutMarket): number {
  return toDisplayAmount(amountEgp, marketOrIsSaudi);
}

export const B2B_TIERS: B2BTierSpec[] = [
  {
    id: "b2b_starter",
    tag: "STARTER",
    name_ar: "باقة القنوات الناشئة (Starter B2B)",
    name_en: "Channel Starter (B2B)",
    amount_egp: 1000,
    daily_limit: 50,
    monthly_est: "1,100",
    max_members_ar: "حتى 150 عضو",
    max_members_en: "Up to 150 members",
    groups_count: 1,
    is_featured: false,
  },
  {
    id: "b2b_pro",
    tag: "PRO VIP",
    name_ar: "باقة المحللين المحترفين (Pro VIP B2B)",
    name_en: "Channel Pro VIP (B2B)",
    amount_egp: 1500,
    daily_limit: 120,
    monthly_est: "2,640",
    max_members_ar: "حتى 500 عضو",
    max_members_en: "Up to 500 members",
    groups_count: 1,
    is_featured: true,
  },
  {
    id: "b2b_enterprise",
    tag: "ENTERPRISE",
    name_ar: "باقة كبار المحللين والشركات (Enterprise B2B)",
    name_en: "Enterprise & Multi-Group",
    amount_egp: 2500,
    daily_limit: 250,
    monthly_est: "5,500",
    max_members_ar: "حتى 1,500 عضو (جروبين)",
    max_members_en: "Up to 1,500 members (2 groups)",
    groups_count: 2,
    is_featured: false,
  },
];

export const B2B_CONTACT = {
  whatsappNumber: "201024359109",
  telegramSupportHandle: "egxbots_support",
  telegramBotHandle: "egxbots_bot",
  supportEmail: "support@egxbots.com",
};
