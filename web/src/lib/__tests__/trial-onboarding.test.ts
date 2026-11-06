import { consumeTrialAutostart, pickTrialVariant, prepareTrialAutostart, TRIAL_PROMPTS } from "../trial-onboarding";

class MemoryStorage {
  private store = new Map<string, string>();
  getItem(key: string) { return this.store.has(key) ? this.store.get(key)! : null; }
  setItem(key: string, value: string) { this.store.set(key, String(value)); }
  removeItem(key: string) { this.store.delete(key); }
  clear() { this.store.clear(); }
}

describe("trial onboarding autostart", () => {
  beforeEach(() => {
    (globalThis as any).localStorage = new MemoryStorage();
    (globalThis as any).sessionStorage = new MemoryStorage();
  });

  it("assigns a stable variant per browser", () => {
    const first = pickTrialVariant();
    expect(["A", "B"]).toContain(first);
    expect(pickTrialVariant()).toBe(first);
  });

  it("carries the prompt once and clears the intent", () => {
    const variant = prepareTrialAutostart();
    const pending = consumeTrialAutostart();
    expect(pending).toEqual({ variant, prompt: TRIAL_PROMPTS[variant] });
    expect(consumeTrialAutostart()).toBeNull();
  });

  it("degrades safely when storage is unavailable", () => {
    delete (globalThis as any).localStorage;
    delete (globalThis as any).sessionStorage;
    expect(pickTrialVariant()).toBe("A");
    expect(consumeTrialAutostart()).toBeNull();
  });
});
