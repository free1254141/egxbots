/**
 * Trial activation onboarding.
 *
 * A trial that never opens the chat converts at 0%. This module carries a
 * one-shot "open the chat and ask the first question" intent from the moment a
 * trial is activated until the chat widget can execute it, and assigns each
 * user to an A/B prompt variant for measurement.
 */

export const TRIAL_AUTOSTART_EVENT = "trial-autostart";

const AUTOSTART_KEY = "egxbots_trial_autostart_v1";
const VARIANT_KEY = "egxbots_trial_variant_v1";

export type TrialPromptVariant = "A" | "B";

export const TRIAL_PROMPTS: Record<TrialPromptVariant, string> = {
  A: "رشّح لي 3 أسهم عليها فرصة شراء النهارده، مع سعر الدخول ووقف الخسارة والهدف",
  B: "حلّل لي سهم COMI فنياً وقولّي مناطق الدخول والخروج المناسبة",
};

export function isTrialPromptVariant(value: unknown): value is TrialPromptVariant {
  return value === "A" || value === "B";
}

/** Stable per-browser assignment so both prompts are measured on comparable users. */
export function pickTrialVariant(): TrialPromptVariant {
  try {
    const stored = localStorage.getItem(VARIANT_KEY);
    if (isTrialPromptVariant(stored)) return stored;
    const assigned: TrialPromptVariant = Math.random() < 0.5 ? "A" : "B";
    localStorage.setItem(VARIANT_KEY, assigned);
    return assigned;
  } catch {
    return "A";
  }
}

/** Record the pending autostart intent and return the assigned variant. */
export function prepareTrialAutostart(): TrialPromptVariant {
  const variant = pickTrialVariant();
  try {
    sessionStorage.setItem(AUTOSTART_KEY, JSON.stringify({
      variant,
      prompt: TRIAL_PROMPTS[variant],
      at: Date.now(),
    }));
  } catch {
    // Storage can be unavailable in private modes; the chat still opens normally.
  }
  return variant;
}

/** One-shot read: the intent is removed so a refresh cannot send it twice. */
export function consumeTrialAutostart(): { variant: TrialPromptVariant; prompt: string } | null {
  try {
    const raw = sessionStorage.getItem(AUTOSTART_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(AUTOSTART_KEY);
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed.prompt !== "string" || !parsed.prompt.trim()) return null;
    return {
      variant: isTrialPromptVariant(parsed.variant) ? parsed.variant : "A",
      prompt: parsed.prompt,
    };
  } catch {
    return null;
  }
}

/** Drop a pending intent when activation did not succeed. */
export function clearTrialAutostart(): void {
  try {
    sessionStorage.removeItem(AUTOSTART_KEY);
  } catch {
    // ignore
  }
}
