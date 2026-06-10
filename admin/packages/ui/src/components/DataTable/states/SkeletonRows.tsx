import { cn } from "../../../utils/cn";

export interface SkeletonRowsProps {
  columnCount: number;
  rowCount?: number;
  density?: "default" | "compact";
}

export function SkeletonRows({
  columnCount,
  rowCount = 8,
  density = "default",
}: SkeletonRowsProps) {
  const heightClass =
    density === "compact"
      ? "h-[var(--height-table-row-compact)]"
      : "h-[var(--height-table-row)]";
  return (
    <>
      {Array.from({ length: rowCount }).map((_, rowIdx) => (
        <tr
          key={`skel-${rowIdx}`}
          className={cn(
            "border-b border-[var(--border-subtle)]",
            heightClass,
          )}
        >
          {Array.from({ length: columnCount }).map((__, colIdx) => (
            <td key={`skel-${rowIdx}-${colIdx}`} className="px-4">
              <span
                className={cn(
                  "block h-3 w-full max-w-[180px] animate-pulse rounded",
                  "bg-gradient-to-r from-[var(--color-gray-200)] via-[var(--color-gray-100)] to-[var(--color-gray-200)]",
                  "[animation-duration:1.4s]",
                )}
              />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
