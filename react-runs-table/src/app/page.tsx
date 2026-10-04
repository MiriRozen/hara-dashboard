import { RunsTable } from "@/components/RunsTable";
import { loadRuns } from "@/lib/load";

export const dynamic = "force-dynamic";

export default async function Page() {
  const { runs, signals } = await loadRuns();
  return (
    <main className="mx-auto max-w-7xl px-4 py-8 md:px-8">
      <header className="mb-6">
        <h1 className="text-3xl font-extrabold">ריצות</h1>
        <p className="text-muted">
          כל הזמנים בשעון ישראל. סכומים בדולר, 4 ספרות אחרי הנקודה. כשהעלות לא סופית מוצג „לפחות“ — זה חסם תחתון, לא הסכום האמיתי.
        </p>
      </header>
      <RunsTable runs={runs} signals={signals} />
    </main>
  );
}
