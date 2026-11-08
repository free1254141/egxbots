import { Metadata } from "next";
import B2BDashboardClient from "./B2BDashboardClient";

export const metadata: Metadata = {
  title: "لوحة تحكم ترخيص بوت التليجرام للقنوات (B2B) | EGX BOTS",
  description: "لوحة إدارة ومتابعة استهلاك بوت التليجرام الخاص بمجموعتك، وتعديل التوقيع المخصص لحسابك.",
};

export default function B2BDashboardPage() {
  return <B2BDashboardClient />;
}
