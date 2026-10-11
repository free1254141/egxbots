/** @jest-environment jsdom */
import React from "react";
import { render, act } from "@testing-library/react";
import ShortSwingTradeChart from "./TradeChart";

const mockChart = jest.fn();
jest.mock("../TradingViewChartDynamic", () => ({
  __esModule: true,
  default: (props: unknown) => {
    mockChart(props);
    return <div data-testid="chart" />;
  },
}));
beforeEach(() => mockChart.mockClear());

test("trade chart has no automatic EMA10 overlay or toggle", () => {
  const view = render(<ShortSwingTradeChart isAr theme="dark" trade={{symbol: "AJWA", entry_date: "2026-10-07", price_date: "2026-10-11", entry_price: 100, trailing_stop: 96, return_pct: 0}} />);
  act(() => mockChart.mock.calls.at(-1)![0].onCandlesLoaded(Array.from({length: 12}, (_, index) => ({time: Date.parse("2026-10-01T00:00:00Z") / 1000 + index * 86400, open: 100, high: 102, low: 99, close: 101, volume: 1000}))));
  expect(mockChart.mock.calls.at(-1)![0].strategyOverlays.map((line: {id: string}) => line.id)).toEqual(["swing-entry", "swing-stop"]);
  expect(view.queryByRole("button", {name: /EMA10/})).toBeNull();
});

test("closed trades carry exact entry/exit markers and known levels without a fabricated target", () => {
  render(
    <ShortSwingTradeChart
      isAr={false}
      theme="dark"
      trade={{
        symbol: "AJWA",
        entry_date: "2026-10-07",
        exit_date: "2026-10-11",
        entry_price: 100,
        exit_price: 110,
        trailing_stop: 105,
        return_pct: 10,
      }}
    />,
  );
  const props = mockChart.mock.calls.at(-1)![0];
  expect(props.exchange).toBe("EGX");
  expect(props.showApiMarkers).toBe(false);
  expect(
    props.customMarkers.map((marker: { text: string }) => marker.text),
  ).toEqual(["Entry", "Exit"]);
  expect(props.customMarkers[0].time).toBe(
    Date.parse("2026-10-07T00:00:00Z") / 1000,
  );
  expect(
    props.strategyOverlays.map((level: { id: string }) => level.id),
  ).toEqual(["swing-entry", "swing-stop", "swing-exit"]);
});

test("pending signal has no executed entry and locked details never mount a chart", () => {
  const view = render(
    <ShortSwingTradeChart
      isAr
      theme="light"
      trade={{
        symbol: "AJWA",
        entry_date: "2026-10-12",
        signal_date: "2026-10-11",
        reference_close: 100,
        is_pending_entry: true,
        return_pct: null,
      }}
    />,
  );
  expect(mockChart.mock.calls.at(-1)![0].customMarkers[0].text).toContain(
    "انتظار التنفيذ",
  );
  view.rerender(
    <ShortSwingTradeChart
      isAr
      theme="light"
      trade={{
        symbol: "SECRET",
        entry_date: "2026-10-07",
        return_pct: null,
        is_locked: true,
      }}
    />,
  );
  expect(view.queryByTestId("chart")).toBeNull();
  expect(view.queryByText("SECRET")).toBeNull();
});
