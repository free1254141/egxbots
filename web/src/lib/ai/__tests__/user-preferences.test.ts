import {
  applyUserRulesToToolArgs,
  buildUserRulesPrompt,
  isShariaPreference,
  mergeUserRule,
} from "../user-preferences";

describe("user standing preferences", () => {
  it("detects a sharia standing rule in Arabic", () => {
    expect(isShariaPreference("من دلوقتي أي توصية تكون في الشريعة")).toBe(true);
    expect(isShariaPreference("أنا عايز أسهم حلال فقط")).toBe(true);
    expect(isShariaPreference("داخل EGX 33 بس")).toBe(true);
    expect(isShariaPreference("أنا سوينغ قصير فقط")).toBe(false);
    expect(isShariaPreference("")).toBe(false);
  });

  it("forces sharia_only on recommendation-like tools", () => {
    const rules = "كل التوصيات تكون متوافقة مع الشريعة";
    for (const tool of ["get_recommendations", "get_technical_scan", "get_accumulation_stocks", "screen_stocks"]) {
      expect(applyUserRulesToToolArgs(tool, {}, rules).sharia_only).toBe(true);
      expect(applyUserRulesToToolArgs(tool, { sharia_only: false }, rules).sharia_only).toBe(true);
      expect(applyUserRulesToToolArgs(tool, {}, "").sharia_only).toBeUndefined();
    }
    expect(applyUserRulesToToolArgs("get_stock", {}, rules).sharia_only).toBeUndefined();
  });

  it("merges a rule once and keeps existing rules", () => {
    const first = mergeUserRule(null, "التوصيات شرعية فقط");
    expect(first).toBe("- التوصيات شرعية فقط");
    const second = mergeUserRule(first, "التوصيات شرعية فقط");
    expect(second).toBe(first);
    const third = mergeUserRule(first, "الإجابات مختصرة");
    expect(third).toBe("- التوصيات شرعية فقط\n- الإجابات مختصرة");
  });

  it("builds an injected prompt only when rules exist", () => {
    expect(buildUserRulesPrompt("")).toBe("");
    const prompt = buildUserRulesPrompt("التوصيات شرعية فقط");
    expect(prompt).toContain("التوصيات شرعية فقط");
    expect(prompt).toContain("sharia_only=true");
  });
});
