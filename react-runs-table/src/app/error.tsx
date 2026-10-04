"use client";

import { useRouter } from "next/navigation";
import { startTransition } from "react";

export default function ErrorView({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const router = useRouter();
  return (
    <main className="mx-auto max-w-xl px-4 py-16 text-center">
      <div role="alert" className="rounded-xl border border-critical bg-critical-bg p-8 text-critical-text">
        <p className="text-lg font-bold">
          <span aria-hidden="true">✖</span> לא הצלחנו לטעון את הריצות
        </p>
        <p className="mt-2 text-sm">אירעה תקלה בטעינת הנתונים. אפשר לנסות שוב; אם התקלה חוזרת, פנו לצוות עם קוד השגיאה.</p>
        {error.digest && (
          <p className="mt-1 text-xs">
            קוד שגיאה: <bdi dir="ltr" className="font-mono">{error.digest}</bdi>
          </p>
        )}
        <button
          type="button"
          onClick={() =>
            startTransition(() => {
              router.refresh();
              reset();
            })
          }
          className="mt-4 rounded-md border border-current px-4 py-1.5"
        >
          לנסות שוב
        </button>
      </div>
    </main>
  );
}
