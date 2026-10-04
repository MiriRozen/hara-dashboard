export default function Loading() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-8 md:px-8" aria-busy="true">
      <p role="status" className="sr-only">טוען ריצות…</p>
      <div className="mb-6 h-9 w-40 animate-pulse rounded bg-track" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-track" />
        ))}
      </div>
      <div className="mt-6 space-y-2">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="h-16 animate-pulse rounded bg-track" />
        ))}
      </div>
    </main>
  );
}
