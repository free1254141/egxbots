import {
  buildUserRulesPrompt,
  mergeUserRule,
  removeUserRule,
  replaceUserRules,
  userRulesList,
} from "../user-preferences";
import { buildAnalysisCacheKey } from "../analysis-cache";

describe("user standing preferences memory", () => {
  it("parses stored rules into a list", () => {
    expect(userRulesList("- قاعدة أولى\n- قاعدة ثانية\n")).toEqual(["- قاعدة أولى", "- قاعدة ثانية"]);
    expect(userRulesList("")).toEqual([]);
    expect(userRulesList(null)).toEqual([]);
  });

  it("merges a rule once and keeps existing rules", () => {
    const first = mergeUserRule(null, "التوصيات شرعية فقط");
    expect(first).toBe("- التوصيات شرعية فقط");
    expect(mergeUserRule(first, "التوصيات شرعية فقط")).toBe(first);
    expect(mergeUserRule(first, "الإجابات مختصرة")).toBe("- التوصيات شرعية فقط\n- الإجابات مختصرة");
  });

  it("removes a rule by matching text without touching the others", () => {
    const existing = "- التوصيات شرعية فقط\n- الإجابات مختصرة\n- تجنب الأسهم الصغيرة";
    const result = removeUserRule(existing, "مختصرة");
    expect(result.removed).toBe(true);
    expect(result.rules).toBe("- التوصيات شرعية فقط\n- تجنب الأسهم الصغيرة");
    expect(removeUserRule(existing, "غير موجود").removed).toBe(false);
  });

  it("replaces the full memory list", () => {
    expect(replaceUserRules(["قاعدة أ", "- قاعدة ب"])).toBe("- قاعدة أ\n- قاعدة ب");
    expect(replaceUserRules([])).toBe("");
  });

  it("injects the full memory plus conflict guidance", () => {
    expect(buildUserRulesPrompt("")).toBe("");
    const prompt = buildUserRulesPrompt("- التوصيات شرعية فقط");
    expect(prompt).toContain("التوصيات شرعية فقط");
    expect(prompt).toContain("تعارضت");
    expect(prompt).toContain("manage_user_preferences");
  });

  it("scopes analysis cache keys by standing user rules without disabling caching", () => {
    const publicKey = buildAnalysisCacheKey("تحليل سهم COMI", ["COMI"], false, null);
    const rulesKeyA = buildAnalysisCacheKey("تحليل سهم COMI", ["COMI"], false, "- التوصيات شرعية فقط");
    const rulesKeyB = buildAnalysisCacheKey("تحليل سهم COMI", ["COMI"], false, "- الإجابات مختصرة");
    expect(publicKey).toBe("vip_stock_COMI");
    expect(rulesKeyA).toMatch(/^vip_stock_COMI_rules_[0-9a-f]{12}$/);
    expect(rulesKeyB).toMatch(/^vip_stock_COMI_rules_[0-9a-f]{12}$/);
    expect(rulesKeyA).not.toBe(publicKey);
    expect(rulesKeyA).not.toBe(rulesKeyB);
  });
});
