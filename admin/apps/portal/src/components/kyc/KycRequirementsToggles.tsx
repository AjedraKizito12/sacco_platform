"use client";

import { Button, Card, Checkbox, Label } from "@sacco/ui";
import type { SaccoKycRequirementItemOut } from "@sacco/schemas";

/**
 * Presentational required-set toggle list shared by the platform SACCO
 * settings page and the operator member settings page. Wrappers own the
 * items state and the save mutation.
 */
export function KycRequirementsToggles({
  items,
  description,
  busy,
  saveLabel = "Save requirements",
  onToggle,
  onSave,
}: {
  items: SaccoKycRequirementItemOut[];
  description: string;
  busy: boolean;
  saveLabel?: string;
  onToggle(key: string, next: boolean): void;
  onSave(): void;
}) {
  return (
    <Card className="flex max-w-xl flex-col gap-4 p-6">
      <p className="text-[13px] text-[var(--text-secondary)]">{description}</p>
      <ul className="flex flex-col">
        {items.map((item) => (
          <li key={item.key} className="flex items-center gap-3 py-2">
            <Checkbox
              id={`req-${item.key}`}
              checked={item.required}
              disabled={item.locked}
              onCheckedChange={(checked) => onToggle(item.key, checked === true)}
            />
            <Label htmlFor={`req-${item.key}`}>{item.label}</Label>
            {item.locked ? (
              <span className="text-[11px] text-[var(--text-tertiary)]">
                Always required
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      <div>
        <Button onClick={onSave} disabled={busy}>
          {saveLabel}
        </Button>
      </div>
    </Card>
  );
}
