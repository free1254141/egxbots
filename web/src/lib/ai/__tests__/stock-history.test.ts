import { summarizeStockHistory } from "../stock-history";
const rows=[{date:"2026-10-11",close:7},{date:"2026-10-07",close:6.50},{date:"2026-10-06",close:6.13},{date:"2026-10-04",close:6.85},{date:"2026-10-01",close:6.18}];
test("weekly baseline and within-week returns are separate",()=>{
    const h=summarizeStockHistory(rows,new Date("2026-10-14T20:00:00Z"));
    expect(h.last_week_summary).toMatchObject({start_date:"2026-10-04",end_date:"2026-10-07",baseline_date:"2026-10-01",baseline_close:6.18,change_pct:5.18,within_week_change_pct:-5.11,corporate_actions_adjusted:false});
});
test("missing prior-week baseline stays unknown",()=>{
    expect(summarizeStockHistory(rows.slice(0,-1),new Date("2026-10-14T20:00:00Z")).last_week_summary?.change_pct).toBeNull();
});
test("Cairo Sunday includes Sunday and excludes prior Saturday",()=>{
    const h=summarizeStockHistory([{date:"2026-10-10",close:100},{date:"2026-10-04",close:50},{date:"2026-10-03",close:25}],new Date("2026-10-10T22:00:00Z"));
    expect(h.last_week_summary).toMatchObject({sessions_count:2,start_date:"2026-10-04",end_date:"2026-10-10",baseline_date:"2026-10-03"});
});
