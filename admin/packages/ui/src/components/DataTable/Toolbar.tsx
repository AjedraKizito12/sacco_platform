import { Download, ListFilter, Rows3, Rows4 } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "../Button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "../DropdownMenu";
import type { Density } from "./types";

export interface ToolbarColumn {
  id: string;
  header: string;
  /** Columns marked `pinned` can't be hidden. */
  pinned?: boolean;
}

export interface ToolbarProps {
  filterSlot?: ReactNode;
  density: Density;
  onDensityChange(d: Density): void;
  columns: ToolbarColumn[];
  hiddenColumnIds: string[];
  onToggleColumn(id: string): void;
  onExportCsv?(): void;
}

export function Toolbar({
  filterSlot,
  density,
  onDensityChange,
  columns,
  hiddenColumnIds,
  onToggleColumn,
  onExportCsv,
}: ToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border-subtle)] px-4 py-3">
      <div className="flex flex-1 flex-wrap items-center gap-2">{filterSlot}</div>
      <Button
        size="sm"
        variant="ghost"
        onClick={() =>
          onDensityChange(density === "compact" ? "default" : "compact")
        }
        aria-label={
          density === "compact"
            ? "Switch to comfortable density"
            : "Switch to compact density"
        }
      >
        {density === "compact" ? (
          <Rows3 size={16} strokeWidth={1.75} />
        ) : (
          <Rows4 size={16} strokeWidth={1.75} />
        )}
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size="sm" variant="ghost" aria-label="Column visibility">
            <ListFilter size={16} strokeWidth={1.75} />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[200px]">
          <DropdownMenuLabel>Columns</DropdownMenuLabel>
          {columns.map((c) => {
            const hidden = hiddenColumnIds.includes(c.id);
            return (
              <DropdownMenuCheckboxItem
                key={c.id}
                checked={!hidden}
                disabled={c.pinned ?? false}
                onCheckedChange={() => onToggleColumn(c.id)}
              >
                {c.header}
              </DropdownMenuCheckboxItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
      {onExportCsv ? (
        <Button
          size="sm"
          variant="ghost"
          onClick={onExportCsv}
          aria-label="Export CSV"
        >
          <Download size={16} strokeWidth={1.75} />
        </Button>
      ) : null}
    </div>
  );
}
