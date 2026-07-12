import {
  navForVariant,
  type ShellVariant,
} from "@/components/shell/nav-config";

export interface NavAction {
  label: string;
  url: string;
}

/**
 * Flatten the nav-config for a variant into "Go to <label>" quick-nav actions
 * (groups → items → item.href, plus each item's children). DRY: the palette's
 * navigation commands come from the same nav definitions the sidebar renders.
 */
export function navActions(variant: ShellVariant): NavAction[] {
  const out: NavAction[] = [];
  const seen = new Set<string>();
  const push = (label: string, url: string | undefined) => {
    if (!url || seen.has(url)) return;
    seen.add(url);
    out.push({ label: `Go to ${label}`, url });
  };
  for (const group of navForVariant(variant)) {
    for (const item of group.items) {
      push(item.label, item.href);
      for (const child of item.children ?? []) push(child.label, child.href);
    }
  }
  return out;
}
