/** @jest-environment jsdom */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import RevenueDetailsModal, { ApprovedOrder } from "../RevenueDetailsModal";

const mockOrders: ApprovedOrder[] = [
  {
    id: "ord_1001_easykash",
    user_id: "u1",
    plan_id: "pro",
    amount_egp: 200,
    net_egp: 192,
    provider: "easykash",
    created_at: "2026-10-26T12:00:00Z",
    email: "customer1@example.com",
    display_name: "Ahmed Ali",
  },
  {
    id: "ord_1002_vodafone",
    user_id: "u2",
    plan_id: "pro",
    amount_egp: 200,
    net_egp: 192,
    provider: "vodafone_cash",
    created_at: "2026-10-26T10:00:00Z",
    email: "customer2@example.com",
    display_name: "Mahmoud Hassan",
  },
  {
    id: "ord_1003_instapay",
    user_id: "u3",
    plan_id: "pro",
    amount_egp: 500,
    net_egp: 480,
    provider: "instapay",
    created_at: "2026-10-25T15:00:00Z",
    email: "customer3@example.com",
    display_name: "Sara Mohamed",
  },
];

describe("RevenueDetailsModal", () => {
  it("does not render when isOpen is false", () => {
    const { container } = render(
      <RevenueDetailsModal
        isOpen={false}
        onClose={jest.fn()}
        orders={mockOrders}
        totalRevenue={864}
        totalPaidOrders={3}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders summary cards and all orders when open", () => {
    render(
      <RevenueDetailsModal
        isOpen={true}
        onClose={jest.fn()}
        orders={mockOrders}
        totalRevenue={864}
        totalPaidOrders={3}
      />
    );

    // Summary cards checks
    expect(screen.getByText("900.00")).toBeTruthy(); // Gross (200 + 200 + 500 = 900)
    expect(screen.getByText("-36.00")).toBeTruthy(); // 4% Gateway fee (900 - 864 = 36)
    expect(screen.getByText("864.00")).toBeTruthy(); // Net revenue
    expect(screen.getAllByText("3").length).toBeGreaterThanOrEqual(1); // Total confirmed orders / row index 3

    // Orders in table
    expect(screen.getByText("Ahmed Ali")).toBeTruthy();
    expect(screen.getByText("customer1@example.com")).toBeTruthy();
    expect(screen.getByText("Mahmoud Hassan")).toBeTruthy();
    expect(screen.getByText("Sara Mohamed")).toBeTruthy();
  });

  it("filters orders by search query", () => {
    render(
      <RevenueDetailsModal
        isOpen={true}
        onClose={jest.fn()}
        orders={mockOrders}
        totalRevenue={864}
        totalPaidOrders={3}
      />
    );

    const searchInput = screen.getByPlaceholderText(/ابحث بالبريد، الاسم/);
    fireEvent.change(searchInput, { target: { value: "Mahmoud" } });

    expect(screen.getByText("Mahmoud Hassan")).toBeTruthy();
    expect(screen.queryByText("Ahmed Ali")).toBeNull();
    expect(screen.queryByText("Sara Mohamed")).toBeNull();
  });

  it("filters orders by provider button", () => {
    render(
      <RevenueDetailsModal
        isOpen={true}
        onClose={jest.fn()}
        orders={mockOrders}
        totalRevenue={864}
        totalPaidOrders={3}
      />
    );

    // Click InstaPay filter
    const instapayBtn = screen.getByRole("button", { name: "InstaPay" });
    fireEvent.click(instapayBtn);

    expect(screen.getByText("Sara Mohamed")).toBeTruthy();
    expect(screen.queryByText("Ahmed Ali")).toBeNull();
    expect(screen.queryByText("Mahmoud Hassan")).toBeNull();
  });

  it("calls onClose when close button is clicked", () => {
    const onClose = jest.fn();
    render(
      <RevenueDetailsModal
        isOpen={true}
        onClose={onClose}
        orders={mockOrders}
        totalRevenue={864}
        totalPaidOrders={3}
      />
    );

    const closeBtn = screen.getByLabelText("إغلاق");
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
