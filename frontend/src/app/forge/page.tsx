import ForgeDashboard from "@/components/forge/ForgeDashboard";
import {
  getHeartbeat,
  getRoadmap,
  getQuality,
  getLogsTail,
} from "@/lib/systemClient";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export const metadata = {
  title: "ATLAS · Forge Build Dashboard",
};

export default async function ForgePage() {
  // Fetch all 4 endpoints in parallel on the server for fast initial render.
  // Failures are graceful — null is passed to the client which handles empty state.
  const [heartbeat, roadmap, quality, log] = await Promise.allSettled([
    getHeartbeat(),
    getRoadmap(),
    getQuality(),
    getLogsTail(200),
  ]);

  return (
    <ForgeDashboard
      initial={{
        heartbeat: heartbeat.status === "fulfilled" ? heartbeat.value : null,
        roadmap: roadmap.status === "fulfilled" ? roadmap.value : null,
        quality: quality.status === "fulfilled" ? quality.value : null,
        log: log.status === "fulfilled" ? log.value : null,
        context: [],
      }}
    />
  );
}
THIS IS A SYNTAX ERROR {{{{
