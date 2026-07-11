"use client";

import { useState } from "react";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  catalogForAudience,
  type NotificationAudience,
  type NotificationChannel,
  type NotificationPreferenceOut,
} from "@sacco/schemas";
import { Button, Card, Checkbox, toast } from "@sacco/ui";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

const CHANNEL_LABELS: Record<NotificationChannel, string> = {
  email: "Email",
  in_app: "In-app",
};

function prefKey(eventCode: string, channel: string) {
  return `${eventCode}:${channel}`;
}

export function NotificationPreferencesForm({
  audience,
  initial,
}: {
  audience: NotificationAudience;
  initial: NotificationPreferenceOut[];
}) {
  const { resources } = useAuth();
  const rows = catalogForAudience(audience);

  // Absence of a stored row = enabled (backend default). Seed local state
  // from the stored rows only; untouched toggles read as true.
  const [prefs, setPrefs] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(
      initial.map((pref) => [prefKey(pref.event_code, pref.channel), pref.enabled]),
    ),
  );

  const isEnabled = (code: string, channel: string) =>
    prefs[prefKey(code, channel)] ?? true;

  const mutation = useTypedMutation<
    unknown,
    { event_code: string; channel: string; enabled: boolean }[]
  >(
    async (matrix) => {
      const res = await (resources.notifications.putPreferences(
        audience,
        matrix,
      ) as Promise<{ data?: NotificationPreferenceOut[]; error?: unknown }>);
      if (res.error) throw res.error;
      return res.data ?? [];
    },
    {
      invalidates: [queryKeys.notifications.preferences(audience)],
      onSuccess: () => toast.success("Notification preferences saved"),
      onError: (error) => {
        toast.error("The preferences were not saved", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const save = () => {
    mutation.mutate(
      rows.flatMap((row) =>
        row.channels.map((channel) => ({
          event_code: row.code,
          channel,
          enabled: isEnabled(row.code, channel),
        })),
      ),
    );
  };

  return (
    <Card className="flex flex-col gap-4 p-6">
      <p className="text-sm text-[var(--text-secondary)]">
        Choose how you want to be notified. All notifications are on by
        default.
      </p>
      <ul className="divide-y divide-[var(--border-subtle)]">
        {rows.map((row) => (
          <li
            key={row.code}
            className="flex flex-wrap items-center justify-between gap-3 py-3"
          >
            <span className="text-sm text-[var(--text-primary)]">{row.label}</span>
            <span className="flex items-center gap-5">
              {row.channels.map((channel) => (
                <label
                  key={channel}
                  className="flex items-center gap-2 text-sm text-[var(--text-secondary)]"
                >
                  <Checkbox
                    aria-label={`${row.label} via ${CHANNEL_LABELS[channel]}`}
                    checked={isEnabled(row.code, channel)}
                    onCheckedChange={(checked) =>
                      setPrefs((prev) => ({
                        ...prev,
                        [prefKey(row.code, channel)]: checked === true,
                      }))
                    }
                  />
                  {CHANNEL_LABELS[channel]}
                </label>
              ))}
            </span>
          </li>
        ))}
      </ul>
      <div>
        <Button onClick={save} disabled={mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Save preferences"}
        </Button>
      </div>
    </Card>
  );
}
