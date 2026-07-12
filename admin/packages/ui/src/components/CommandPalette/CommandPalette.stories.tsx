import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { CommandPalette, type CommandPaletteItem } from "./CommandPalette";

const items: CommandPaletteItem[] = [
  { id: "1", title: "Grace Namono", subtitle: "M-0001", url: "/members/1", group: "Members" },
  { id: "2", title: "John Okello", subtitle: "M-0002", url: "/members/2", group: "Members" },
  { id: "3", title: "Demo SACCO", subtitle: "demo-sacco", url: "/platform/tenants/3", group: "Tenants" },
];

const meta: Meta<typeof CommandPalette> = {
  title: "Shell/CommandPalette",
  component: CommandPalette,
  parameters: { layout: "fullscreen" },
};
export default meta;
type Story = StoryObj<typeof CommandPalette>;

function Harness({ initialItems, loading = false }: { initialItems: CommandPaletteItem[]; loading?: boolean }) {
  const [open, setOpen] = useState(true);
  const [query, setQuery] = useState("gr");
  return (
    <CommandPalette
      open={open}
      onOpenChange={setOpen}
      query={query}
      onQueryChange={setQuery}
      items={initialItems}
      loading={loading}
      onSelect={(i) => alert(i.url)}
    />
  );
}

export const Default: Story = { render: () => <Harness initialItems={items} /> };
export const Loading: Story = { render: () => <Harness initialItems={[]} loading /> };
export const Empty: Story = { render: () => <Harness initialItems={[]} /> };
