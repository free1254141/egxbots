/**
 * Portfolio entitlement limits.
 *
 * Pro tracks up to 15 stocks (was 10). The limit must come from one source of
 * truth (plan-gate + env), not a hard-coded constant inside a route.
 */
describe("portfolio plan limits", () => {
  const originalPro = process.env.PRO_PORTFOLIO_STOCKS;
  const originalFree = process.env.FREE_PORTFOLIO_STOCKS;
  const originalPayments = process.env.PAYMENTS_ENABLED;

  beforeEach(() => {
    // Paid plans only exist when billing is enabled; otherwise the platform is
    // free-unlimited by design.
    process.env.PAYMENTS_ENABLED = "true";
  });

  afterEach(() => {
    if (originalPro === undefined) delete process.env.PRO_PORTFOLIO_STOCKS;
    else process.env.PRO_PORTFOLIO_STOCKS = originalPro;
    if (originalFree === undefined) delete process.env.FREE_PORTFOLIO_STOCKS;
    else process.env.FREE_PORTFOLIO_STOCKS = originalFree;
    if (originalPayments === undefined) delete process.env.PAYMENTS_ENABLED;
    else process.env.PAYMENTS_ENABLED = originalPayments;
    jest.resetModules();
  });

  test("pro defaults to 15 portfolio stocks and free stays at 5", async () => {
    delete process.env.PRO_PORTFOLIO_STOCKS;
    delete process.env.FREE_PORTFOLIO_STOCKS;
    jest.resetModules();
    const { planLimits } = await import("../plan-gate");
    expect(planLimits("pro").portfolio_stocks).toBe(15);
    expect(planLimits("free").portfolio_stocks).toBe(5);
  });

  test("PRO_PORTFOLIO_STOCKS overrides the default without code changes", async () => {
    process.env.PRO_PORTFOLIO_STOCKS = "25";
    jest.resetModules();
    const { planLimits } = await import("../plan-gate");
    expect(planLimits("pro").portfolio_stocks).toBe(25);
  });
});
