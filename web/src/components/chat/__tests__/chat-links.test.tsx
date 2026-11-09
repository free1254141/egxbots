/** @jest-environment jsdom */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { FormattedChatMessage } from "../FormattedChatMessage";

describe("FormattedChatMessage Markdown Links", () => {
    it("renders internal platform tool links as clickable anchors with correct href", () => {
        const text = `
يمكنك متابعة الصفقات من:
1. [صفحة الصفقات والمسح الفني](/scanner)
2. [كاشف المصائد والانعكاسات](/scanner/technical)
3. [النماذج المتكررة (شبه ده)](/scanner/backtests?tab=similarity)
4. [رادار إفصاحات الشركات](/disclosures)
5. [شارت الأسهم اللحظي](/chart)
6. [المحفظة الاستثمارية](/portfolio)
        `;

        render(<FormattedChatMessage role="assistant" content={text} />);

        const scannerLink = screen.getByRole("link", { name: "صفحة الصفقات والمسح الفني" });
        expect(scannerLink).toBeInTheDocument();
        expect(scannerLink).toHaveAttribute("href", "/scanner");

        const trapLink = screen.getByRole("link", { name: "كاشف المصائد والانعكاسات" });
        expect(trapLink).toBeInTheDocument();
        expect(trapLink).toHaveAttribute("href", "/scanner/technical");

        const similarityLink = screen.getByRole("link", { name: "النماذج المتكررة (شبه ده)" });
        expect(similarityLink).toBeInTheDocument();
        expect(similarityLink).toHaveAttribute("href", "/scanner/backtests?tab=similarity");

        const disclosuresLink = screen.getByRole("link", { name: "رادار إفصاحات الشركات" });
        expect(disclosuresLink).toBeInTheDocument();
        expect(disclosuresLink).toHaveAttribute("href", "/disclosures");

        const chartLink = screen.getByRole("link", { name: "شارت الأسهم اللحظي" });
        expect(chartLink).toBeInTheDocument();
        expect(chartLink).toHaveAttribute("href", "/chart");

        const portfolioLink = screen.getByRole("link", { name: "المحفظة الاستثمارية" });
        expect(portfolioLink).toBeInTheDocument();
        expect(portfolioLink).toHaveAttribute("href", "/portfolio");
    });

    it("beautifies ugly raw route links like [scanner/](/scanner/) or [/scanner](/scanner)", () => {
        const text = `المصدر: [scanner/](/scanner/)`;
        render(<FormattedChatMessage role="assistant" content={text} />);

        const beautifiedLink = screen.getByRole("link", { name: "صفحة الصفقات والمسح الفني" });
        expect(beautifiedLink).toBeInTheDocument();
        expect(beautifiedLink).toHaveAttribute("href", "/scanner/");
    });
});
