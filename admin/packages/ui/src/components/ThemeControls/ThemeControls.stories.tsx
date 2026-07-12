import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import type { ThemeMode, ThemePrefs } from "@sacco/schemas";
import { THEME_DEFAULTS } from "@sacco/schemas";
import { ThemeControls } from "./ThemeControls";
import { ThemeModeToggle } from "./ThemeModeToggle";

const meta: Meta<typeof ThemeControls> = {
  title: "Primitives/ThemeControls",
  component: ThemeControls,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj;

function Controls({ initial }: { initial: ThemePrefs }) {
  const [prefs, setPrefs] = useState<ThemePrefs>(initial);
  return (
    <div style={{ width: 420 }}>
      <ThemeControls value={prefs} onChange={setPrefs} />
      <p style={{ marginTop: 16, fontSize: 12 }}>state: {JSON.stringify(prefs)}</p>
    </div>
  );
}

function ModeToggle() {
  const [mode, setMode] = useState<ThemeMode>("light");
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <ThemeModeToggle value={mode} onChange={setMode} />
      <span style={{ fontSize: 12 }}>mode: {mode}</span>
    </div>
  );
}

export const Default: Story = {
  name: "Default (system/default/default)",
  render: () => <Controls initial={THEME_DEFAULTS} />,
};

export const LightMode: Story = {
  render: () => <Controls initial={{ mode: "light", accent: "blue", fontSize: "compact" }} />,
};

export const DarkMode: Story = {
  render: () => <Controls initial={{ mode: "dark", accent: "green", fontSize: "large" }} />,
};

export const SystemMode: Story = {
  render: () => <Controls initial={{ mode: "system", accent: "slate", fontSize: "xl" }} />,
};

export const ModeToggleButton: Story = {
  name: "ThemeModeToggle",
  render: () => <ModeToggle />,
};
