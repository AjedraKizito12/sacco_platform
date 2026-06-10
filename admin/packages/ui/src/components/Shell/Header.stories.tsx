import type { Meta, StoryObj } from "@storybook/react";
import { Header } from "./Header";
import { TenantIndicator } from "./TenantIndicator";
import { CommandPaletteTrigger } from "./CommandPaletteTrigger";
import { NotificationBellStub } from "./NotificationBellStub";
import { UserMenu } from "./UserMenu";

const meta: Meta<typeof Header> = {
  title: "Shell/Header",
  component: Header,
  parameters: { layout: "fullscreen" },
};
export default meta;
type Story = StoryObj<typeof Header>;

const Logo = () => (
  <span className="text-[14px] font-semibold tracking-tight">SACCO</span>
);

export const Platform: Story = {
  args: {
    logo: <Logo />,
    center: <CommandPaletteTrigger onActivate={() => {}} />,
    end: (
      <>
        <NotificationBellStub />
        <UserMenu
          fullName="Jane Operator"
          email="jane@platform.example"
          contextLabel="Superuser"
          onSignOut={() => {}}
        />
      </>
    ),
  },
};

export const TenantContext: Story = {
  args: {
    logo: <Logo />,
    start: <TenantIndicator tenantName="Sacco One" />,
    center: <CommandPaletteTrigger onActivate={() => {}} />,
    end: (
      <>
        <NotificationBellStub />
        <UserMenu
          fullName="Mary Operator"
          email="mary@sacco-one.example"
          contextLabel="Admin"
          onSignOut={() => {}}
        />
      </>
    ),
  },
};

export const Impersonating: Story = {
  args: {
    logo: <Logo />,
    start: <TenantIndicator tenantName="Sacco One" impersonating />,
    center: <CommandPaletteTrigger onActivate={() => {}} />,
    end: (
      <>
        <NotificationBellStub />
        <UserMenu
          fullName="Jane Operator"
          email="jane@platform.example"
          contextLabel="Impersonating · ends 14:35 EAT"
          onSignOut={() => {}}
        />
      </>
    ),
  },
};
