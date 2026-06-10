import type { Meta, StoryObj } from "@storybook/react";
import type { ColumnDef } from "@tanstack/react-table";
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

// Storybook-only mocks for TableUrlState. Production callers use
// useTableUrlState(); these constants exist so stories don't need React
// hooks (which would violate the rules-of-hooks lint inside render fns).
function mockUrlState(initial: Partial<TableUrlState> = {}): TableUrlState {
  return {
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
}

const DEFAULT_URL_STATE = mockUrlState();
const FILTERED_URL_STATE = mockUrlState({ filters: { name: "ZZZ" } });
const COMPACT_URL_STATE = mockUrlState({ density: "compact" });

export const WithData: Story = {
  render: () => (
    <DataTable
      id="story-with-data"
      columns={sampleColumns}
      data={sampleData}
      state={{
        totalRows: sampleData.length,
        isError: false,
        isPermissionDenied: false,
      }}
      urlState={DEFAULT_URL_STATE}
      emptyState={{
        title: "No members",
        description: "Register one to get started.",
      }}
    />
  ),
};

export const Loading: Story = {
  render: () => (
    <DataTable
      id="story-loading"
      columns={sampleColumns}
      data={undefined}
      state={{ totalRows: 0, isError: false, isPermissionDenied: false }}
      urlState={DEFAULT_URL_STATE}
      emptyState={{ title: "No members" }}
    />
  ),
};

export const Empty: Story = {
  render: () => (
    <DataTable
      id="story-empty"
      columns={sampleColumns}
      data={[]}
      state={{ totalRows: 0, isError: false, isPermissionDenied: false }}
      urlState={DEFAULT_URL_STATE}
      emptyState={{
        title: "No members",
        description: "Register your first member to get started.",
      }}
    />
  ),
};

export const FilterEmpty: Story = {
  render: () => (
    <DataTable
      id="story-filter-empty"
      columns={sampleColumns}
      data={[]}
      state={{ totalRows: 0, isError: false, isPermissionDenied: false }}
      urlState={FILTERED_URL_STATE}
      emptyState={{ title: "No members" }}
    />
  ),
};

export const Error: Story = {
  render: () => (
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
      urlState={DEFAULT_URL_STATE}
      emptyState={{ title: "No members" }}
    />
  ),
};

export const PermissionDenied: Story = {
  render: () => (
    <DataTable
      id="story-perm"
      columns={sampleColumns}
      data={undefined}
      state={{ totalRows: 0, isError: false, isPermissionDenied: true }}
      urlState={DEFAULT_URL_STATE}
      emptyState={{ title: "No members" }}
    />
  ),
};

export const WithBulk: Story = {
  render: () => (
    <DataTable<SampleRow>
      id="story-bulk"
      columns={sampleColumns}
      data={sampleData}
      state={{
        totalRows: sampleData.length,
        isError: false,
        isPermissionDenied: false,
      }}
      urlState={DEFAULT_URL_STATE}
      emptyState={{ title: "No members" }}
      bulk={{
        actions: [
          { id: "export", label: "Export selected" },
          { id: "suspend", label: "Suspend", destructive: true },
        ],
        onActionOnPage: (ctx, a) => {
          console.log(`Page action ${a}: ${ctx.selectedIds.length}`);
        },
      }}
    />
  ),
};

export const Compact: Story = {
  render: () => (
    <DataTable
      id="story-compact"
      columns={sampleColumns}
      data={sampleData}
      state={{
        totalRows: sampleData.length,
        isError: false,
        isPermissionDenied: false,
      }}
      urlState={COMPACT_URL_STATE}
      emptyState={{ title: "No members" }}
    />
  ),
};
