import ForgeDashboard from "@/components/forge/ForgeDashboard";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export const metadata = {
  title: "ATLAS · Forge Build Dashboard",
};

export default function ForgePage() {
  return <ForgeDashboard />;
}
