"use client";

import { queryKeys, useTypedQuery } from "@sacco/api-client";
import type { SearchHitOut, SearchResultsOut } from "@sacco/schemas";
import { CommandPalette, type CommandPaletteItem } from "@sacco/ui";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/auth/use-auth";

const DEBOUNCE_MS = 200;

const GROUP_LABEL: Record<string, string> = {
  member: "Members",
  tenant: "Tenants",
};

interface AppShellCommandPaletteProps {
  // Only platform + operator (tenant) get search; member has none.
  variant: "platform" | "tenant";
  open: boolean;
  onOpenChange(open: boolean): void;
}

/**
 * Shell command palette (⌘K). Debounces the query and fetches the audience's
 * search endpoint via TanStack Query, then navigates to the selected record.
 * A shell-level client-fetch widget, like the notification bell (contract M).
 */
export function AppShellCommandPalette({
  variant,
  open,
  onOpenChange,
}: AppShellCommandPaletteProps) {
  const { resources } = useAuth();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [query]);

  const enabled = open && debounced.trim().length > 0;
  const keyFn = variant === "platform" ? queryKeys.search.platform : queryKeys.search.tenant;

  const results = useTypedQuery<SearchResultsOut>(
    keyFn(debounced),
    async () => {
      const call =
        variant === "platform"
          ? resources.search.platformSearch(debounced)
          : resources.search.tenantSearch(debounced);
      const res = await (call as Promise<{
        data?: SearchResultsOut;
        error?: unknown;
      }>);
      if (res.error) throw res.error;
      return res.data ?? { hits: [], took_ms: 0 };
    },
    { enabled },
  );

  const items: CommandPaletteItem[] = (results.data?.hits ?? []).map(
    (hit: SearchHitOut) => ({
      id: hit.id,
      title: hit.title,
      subtitle: hit.subtitle,
      url: hit.url,
      group: GROUP_LABEL[hit.entity_type] ?? hit.entity_type,
    }),
  );

  return (
    <CommandPalette
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) setQuery("");
      }}
      query={query}
      onQueryChange={setQuery}
      items={enabled ? items : []}
      loading={enabled && results.isFetching}
      onSelect={(item) => {
        onOpenChange(false);
        setQuery("");
        router.push(item.url);
      }}
    />
  );
}
