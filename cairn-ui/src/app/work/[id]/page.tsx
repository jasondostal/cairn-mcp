"use client";

/**
 * Deep link landing page for work items.
 *
 * ntfy push notifications link to /work/{display_id} (e.g., /work/ca-42).
 * This page fetches the work item by display_id, then opens it on the
 * work items page via ?selected={numeric_id}.
 *
 * Part of ca-259: ntfy deep link -> gate response mobile flow.
 */

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function WorkItemDeepLink() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params.id) return;

    api.workItem(params.id)
      .then((detail) => {
        router.replace(`/work-items?selected=${detail.id}`);
      })
      .catch(() => {
        setError(`Work item "${params.id}" not found`);
      });
  }, [params.id, router]);

  if (error) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center space-y-2">
          <p className="text-sm text-muted-foreground">{error}</p>
          <a href="/work-items" className="text-sm text-primary hover:underline">
            Go to work items
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center h-screen">
      <p className="text-sm text-muted-foreground">Loading work item...</p>
    </div>
  );
}
