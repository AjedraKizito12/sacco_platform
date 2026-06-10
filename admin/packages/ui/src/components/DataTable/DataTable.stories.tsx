import type { Meta, StoryObj } from "@storybook/react";
import type { ColumnDef } from "@tanstack/react-table";
import { useState } from "react";
import { DataTable } from "./DataTable";
import type { TableUrlState } from "./types";

const meta: Meta<typeof DataTable> = {
  title: "Display/DataTable",
  component: DataTable,
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj;

interface SampleRow {
  id: string;
  member: string;
  amount: string;
  status: string;
}

const sampleColumns: ColumnDef<SampleRow>[] = [
  { id: "member", accessorKey: "member", header: "Member" },
  { id: "amount", accessorKey: "amount", header: "Amount" },
  { id: "status", accessorKey: "status", header: "Status" },
];

const sampleData: SampleRow[] = [
  { id: "1", member: "Mary Akello", amount: "UGX 1,234,567", status: "Active" },
  { id: "2", member: "John Mukasa", amount: "UGX 250,000", status: "Dormant" },
  { id: "3", member: "Sarah Achieng", amount: "UGX 5,000,000", status: "Active" },
];

function fakeUrlState(initial: Partial<TableUrlState> = {}): TableUrlState {
  // Storybook-only mock — production uses useTableUrlState.
  const state: TableUrlState = {
    page: 1,
    pageSize: 25,
    sortColumn: null,
    sortDirection: "desc",
    filters: {},
    density: "default",
    setPage: () => {},
    setPageSize: () => {},
    setSort: () => {},
    setFilter: () => {},
    setFilters: () => {},
    setDensity: () => {},
    reset: () => {},
    ...initial,
  };
  return state;
}

export const WithData: Story = {
  render: () => {
    const [urlState] = useState(() => fakeUrlState());
    return (
      <DataTable
        id="story-with-data"
        columns={sampleColumns}
        data={sampleData}
        state={{
          totalRows: sampleData.length,
          isError: false,
          isPermissionDenied: false,
        }}
        urlState={urlState}
        emptyState={{
          title: "No members",
          description: "Register one to get started.",
        }}
      />
    );
  },
};

export const Loading: Story = {
  render: () => {
    const [urlState] = useState(() => fakeUrlState());
    return (
      <DataTable
        id="story-loading"
        columns={sampleColumns}
        data={undefined}
        state={{ totalRows: 0, isError: false, isPermissionDenied: false }}
        urlState={urlState}
        emptyState={{ title: "No members" }}
      />
    );
  },
};

export const Empty: Story = {
  render: () => {
    const [urlState] = useState(() => fakeUrlState());
    return (
      <DataTable
        id="story-empty"
        columns={sampleColumns}
        data={[]}
        state={{ totalRows: 0, isError: false, isPermissionDenied: false }}
        urlState={urlState}
        emptyState={{
          title: "No members",
          description: "Register your first member to get started.",
        }}
      />
    );
  },
};

export const FilterEmpty: Story = {
  render: () => {
    const [urlState] = useState(() =>
      fakeUrlState({ filters: { name: "ZZZ" } }),
    );
    return (
      <DataTable
        id="story-filter-empty"
        columns={sampleColumns}
        data={[]}
        state={{ totalRows: 0, isError: false, isPermissionDenied: false }}
        urlState={urlState}
        emptyState={{ title: "No members" }}
      />
    );
  },
};

export const Error: Story = {
  render: () => {
    const [urlState] = useState(() => fakeUrlState());
    return (
      <DataTable
        id="story-error"
        columns={sampleColumns}
        data={undefined}
        state={{
          totalRows: 0,
          isError: true,
          isPermissionDenied: false,
          error: {
            message: "The members endpoint returned 503.",
            requestId: "req-abc-123",
          },
        }}
        urlState={urlState}
        emptyState={{ title: "No members" }}
      />
    );
  },
};

export const PermissionDenied: Story = {
  render: () => {
    const [urlState] = useState(() => fakeUrlState());
    return (
      <DataTable
        id="story-perm"
        columns={sampleColumns}
        data={undefined}
        state={{ totalRows: 0, isError: false, isPermissionDenied: true }}
        urlState={urlState}
        emptyState={{ title: "No members" }}
      />
    );
  },
};

export const WithBulk: Story = {
  render: () => {
    const [urlState] = useState(() => fakeUrlState());
    return (
      <DataTable<SampleRow>
        id="story-bulk"
        columns={sampleColumns}
        data={sampleData}
        state={{
          totalRows: sampleData.length,
          isError: false,
          isPermissionDenied: false,
        }}
        urlState={urlState}
        emptyState={{ title: "No members" }}
        bulk={{
          actions: [
            { id: "export", label: "Export selected" },
            { id: "suspend", label: "Suspend", destructive: true },
          ],
          onActionOnPage: (ctx, a) =>
            // eslint-disable-next-line no-alert
            alert(`Page action ${a}: ${ctx.selectedIds.length}`),
        }}
      />
    );
  },
};

export const Compact: Story = {
  render: () => {
    const [urlState] = useState(() =>
      fakeUrlState({ density: "compact" }),
    );
    return (
      <DataTable
        id="story-compact"
        columns={sampleColumns}
        data={sampleData}
        state={{
          totalRows: sampleData.length,
          isError: false,
          isPermissionDenied: false,
        }}
        urlState={urlState}
        emptyState={{ title: "No members" }}
      />
    );
  },
};
