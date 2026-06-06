# SACCO SaaS Design System

**Version 2.0**

---

## Overview

This design system defines the visual language, interaction patterns, and UI standards for the SACCO Management Platform.

The system is built for an operational financial tool — used eight hours a day by people whose mistakes cost money. It is inspired by modern fintech SaaS products and emphasizes:

- Trust
- Clarity
- Speed
- Information density
- Error prevention
- Accessibility
- Scalability

The platform should feel premium, professional, and data-focused while remaining approachable for SACCO administrators, managers, accountants, tellers, and members.

---

## Design Principles

### 1. Clarity Over Decoration

Financial information must always be easier to read than decorative elements. Numbers, statuses, and balances are the product.

### 2. Consistency Everywhere

Components behave the same way across all modules. A button, a table row, a money cell, a status badge — identical wherever they appear.

### 3. Data First

The interface prioritizes transactions, balances, schedules, reports, and operational data. Whitespace serves data, not the other way around.

### 4. Accessibility by Default

Every component is keyboard-accessible and meets WCAG AA standards. Operators with disabilities exist; regulators care.

### 5. Enterprise Calm

Avoid excessive colors, gradients, animations, and visual clutter. Monochrome-first. Color is a signal, not a decoration.

### 6. Error Prevention Over Error Recovery

A confirm dialog is cheaper than a reversal. A read-only field is safer than a recoverable mistake. Design assuming the user is tired and the data is sensitive.

### 7. Speed Is a Feature

Pages load fast. Tables paginate server-side. Power users use keyboard shortcuts. Every interaction respects the operator's time.

---

## Typography

### Primary Font

```css
font-family: "General Sans", "Inter", system-ui, sans-serif;
```

General Sans is the primary face for its slightly warmer character; Inter is the fallback. Both support tabular numerals, which is non-negotiable for this system.

### Font Scale

| Style       | Size | Weight |
|-------------|------|--------|
| Display     | 48px | 700    |
| H1          | 36px | 700    |
| H2          | 30px | 700    |
| H3          | 24px | 600    |
| H4          | 20px | 600    |
| H5          | 18px | 600    |
| Body Large  | 16px | 400    |
| Body        | 14px | 400    |
| Small       | 12px | 400    |
| Caption     | 11px | 400    |

### Font Weights

```css
Regular:  400;
Medium:   500;
Semibold: 600;
Bold:     700;
```

### Line Heights

```css
Headings: 120%;
Body:     150%;
```

### Tabular Numerals — Mandatory for Numbers

All numeric displays (balances, amounts, percentages, counts, dates, times) **must** use tabular figures so columns align visually.

```css
.font-tabular {
  font-feature-settings: "tnum" 1, "lnum" 1;
  font-variant-numeric: tabular-nums lining-nums;
}
```

The `<Money>`, `<FormattedDate>`, `<FormattedDateTime>`, `<Percentage>`, and `<Count>` components apply this automatically. Numeric table cells must apply it. Raw numeric strings in JSX must apply it.

---

## Color System

### Neutral Palette

```css
--black:    #1F1F1F;

--gray-900: #2B2B2B;
--gray-800: #3D3D3D;
--gray-700: #5B5B5B;
--gray-600: #767676;
--gray-500: #9A9A9A;
--gray-400: #BDBDBD;
--gray-300: #D9D9D9;
--gray-200: #EDEDED;
--gray-100: #F4F4F4;
--gray-50:  #F8F8F8;

--white:    #FFFFFF;
```

### Primary Colors

```css
--primary-900: #111111;
--primary-800: #1F1F1F;
--primary-700: #2A2A2A;
--primary-600: #333333;
```

Used for primary buttons, navigation chrome, active states, and headings.

### Semantic Colors

#### Success

```css
--success-900: #0E5A3B;
--success-700: #157347;
--success-500: #22C55E;
--success-100: #DCFCE7;
```

Use for: savings growth, successful transactions, positive balances, approved actions, paid status.

#### Warning

```css
--warning-900: #78350F;
--warning-700: #B45309;
--warning-500: #F59E0B;
--warning-100: #FEF3C7;
```

Use for: pending approvals, upcoming repayments, attention-required items, partial payments.

#### Danger

```css
--danger-900: #7F1D1D;
--danger-700: #B91C1C;
--danger-500: #EF4444;
--danger-100: #FEE2E2;
```

Use for: arrears, rejections, failed transactions, write-offs, destructive actions.

#### Information

```css
--info-900: #1E3A8A;
--info-700: #1D4ED8;
--info-500: #3B82F6;
--info-100: #DBEAFE;
```

Use for: notifications, informational messages, system updates, focus rings.

#### Accent (Neutral Highlight)

```css
--accent-700: #5B21B6;
--accent-100: #EDE9FE;
```

Use sparingly for: draft / in-progress states, neutral non-semantic emphasis.

### Color Contrast Matrix — Text on Background

WCAG AA requires 4.5:1 for body text and 3:1 for large text (18px+ or 14px bold). The following matrix tells you which combinations are safe.

| Foreground       | On white | On gray-50 | On gray-100 | On gray-900 | Verdict |
|------------------|----------|------------|-------------|-------------|---------|
| gray-900         | ✓ AAA    | ✓ AAA      | ✓ AAA       | ✗           | Primary text |
| gray-700         | ✓ AAA    | ✓ AAA      | ✓ AA        | ✗           | Secondary text |
| gray-600         | ✓ AA     | ✓ AA       | ✗           | ✗           | Tertiary text, labels |
| gray-500         | ✗ (3.0)  | ✗          | ✗           | ✗           | **Placeholder/disabled only** |
| white            | ✗        | ✗          | ✗           | ✓ AAA       | Inverse text |
| success-700      | ✓ AA     | ✓ AA       | ✓ AA        | ✗           | Success text |
| success-500      | ✗ (2.5)  | ✗          | ✗           | ✓           | **Background/icon only on light** |
| warning-700      | ✓ AA     | ✓ AA       | ✓ AA        | ✗           | Warning text |
| warning-500      | ✗ (2.6)  | ✗          | ✗           | ✓           | **Background/icon only on light** |
| danger-700       | ✓ AA     | ✓ AA       | ✓ AA        | ✗           | Danger text |
| danger-500       | ✗ (3.8)  | ✗          | ✗           | ✓           | **Background/icon, large text only** |
| info-700         | ✓ AA     | ✓ AA       | ✓ AA        | ✗           | Info text, links |
| info-500         | ✗ (3.7)  | ✗          | ✗           | ✓           | **Background/icon only on light** |

**Rules:**
- Primary text: `gray-900`
- Secondary text: `gray-700`
- Tertiary text and form labels: `gray-600`
- Placeholder, disabled, helper-text-on-light: `gray-500` (only because they're not load-bearing)
- Semantic text: always use the `-700` stop; never the `-500` stop on light backgrounds

---

## Layout System

### Application Structure

```
┌─────────────────────────────────────┐
│ Header (56px)                       │
├────────────┬────────────────────────┤
│ Sidebar    │ Main Content           │
│ (260px)    │ (max-width 1440px)     │
│            │                        │
└────────────┴────────────────────────┘
```

### Sidebar

```css
Width:          260px;
Collapsed:      72px;
Background:     #FFFFFF;
Border-right:   1px solid #EDEDED;
```

### Header

```css
Height:         56px;
Background:     #FFFFFF;
Border-bottom:  1px solid #EDEDED;
```

Contains: tenant indicator, command palette trigger (`Cmd+K`), notifications, user menu.

### Content Container

```css
Max width:      1440px;
Margin:         0 auto;
Padding:        24px 32px;
```

---

## Spacing System

8-point base grid, with 4-point increments allowed for component heights only.

| Token | Value |
|-------|-------|
| 0     | 0px   |
| 0.5   | 2px   |
| 1     | 4px   |
| 2     | 8px   |
| 3     | 12px  |
| 4     | 16px  |
| 5     | 20px  |
| 6     | 24px  |
| 8     | 32px  |
| 10    | 40px  |
| 12    | 48px  |
| 16    | 64px  |
| 20    | 80px  |
| 24    | 96px  |

**Rules:**
- Layout spacing snaps to 8px (token-2 increments)
- Component heights and small internal padding may snap to 4px
- Never use arbitrary values in Tailwind classes

---

## Border Radius

```css
--radius-sm:   8px;   /* small chips, badges */
--radius-md:   12px;  /* buttons, inputs, selects */
--radius-lg:   16px;  /* dropdowns, popovers */
--radius-xl:   20px;  /* modals, sheets */
--radius-card: 18px;  /* standard cards */
```

---

## Shadows

```css
--shadow-sm:   0 1px 2px rgba(0,0,0,.05);   /* default cards */
--shadow-md:   0 4px 12px rgba(0,0,0,.08);  /* dropdowns, popovers */
--shadow-lg:   0 8px 24px rgba(0,0,0,.12);  /* modals, sheets */
--shadow-focus: 0 0 0 3px rgba(59,130,246,.25); /* focus ring halo */
```

---

## Component Heights

All interactive controls use the same base height for vertical alignment.

```css
--height-control: 40px;   /* buttons, inputs, selects, date pickers */
--height-control-sm: 32px; /* compact mode, inline controls */
--height-control-lg: 48px; /* primary CTAs in marketing/sign-in screens only */

--height-table-header: 44px;
--height-table-row:    52px;     /* default density */
--height-table-row-compact: 40px; /* compact density */
```

**Rule:** Buttons and inputs that appear in the same row must share the same height. The default for in-app forms and toolbars is 40px.

---

## Focus States

WCAG AA requires visible focus on all interactive elements. Never set `outline: none` without a replacement.

```css
.focus-ring {
  outline: 2px solid var(--info-500);
  outline-offset: 2px;
  border-radius: inherit;
}

/* Tailwind */
.focus-visible:ring-2 .focus-visible:ring-info-500 .focus-visible:ring-offset-2
```

- Default focus: 2px solid `info-500`, offset 2px
- Inside-only focus (for elements that can't show outer ring): inner ring + halo via `--shadow-focus`
- Focus is visible only via `:focus-visible` (keyboard / programmatic), not on mouse click
- Respect `:focus-visible` everywhere; don't show focus rings on mouse-clicked buttons

---

## Motion

Subtle and consistent. Respects `prefers-reduced-motion`.

```css
--ease-out:  cubic-bezier(0.16, 1, 0.3, 1);
--ease-in:   cubic-bezier(0.4, 0, 1, 1);
--ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);

--duration-fast:   150ms;  /* hover, toggle, small state changes */
--duration-medium: 200ms;  /* dropdowns, popovers, tooltips */
--duration-slow:   300ms;  /* modals, sheets, page transitions */
```

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

No bouncing, spinning, parallax, or attention-seeking motion. Animations communicate state changes, never decoration.

---

## Buttons

### Primary

```css
background:    #1F1F1F;
color:         #FFFFFF;
height:        40px;
border-radius: 12px;
padding:       0 16px;
font-weight:   500;
```

Hover: `background: #2A2A2A;`
Active: `background: #111111;`
Disabled: `background: #BDBDBD; color: #FFFFFF; cursor: not-allowed;`

Use for: the primary affordance per screen. One per screen, typically.

### Secondary

```css
background:    #FFFFFF;
border:        1px solid #D9D9D9;
color:         #1F1F1F;
height:        40px;
border-radius: 12px;
padding:       0 16px;
```

Hover: `background: #F8F8F8;`

### Ghost

```css
background: transparent;
color:      #5B5B5B;
height:     40px;
padding:    0 12px;
```

Hover: `background: #F4F4F4; color: #1F1F1F;`

### Destructive

```css
background: #B91C1C;
color:      #FFFFFF;
height:     40px;
```

Hover: `background: #991B1B;`

Use only in confirm dialogs and only when the action is irreversible without administrator help.

### Button Sizes

```css
sm: height 32px, padding 0 12px, font-size 13px;
md: height 40px, padding 0 16px, font-size 14px;  /* default */
lg: height 48px, padding 0 20px, font-size 15px;
```

### Icon Buttons

Square, same height as text buttons. Always include `aria-label`.

```css
40x40px, border-radius 12px
```

---

## Cards

### Standard Card

```css
background:    #FFFFFF;
border:        1px solid #EDEDED;
border-radius: 18px;
padding:       24px;
box-shadow:    var(--shadow-sm);
```

### Section Card (for grouping in detail views)

```css
background:    #FFFFFF;
border:        1px solid #EDEDED;
border-radius: 18px;
padding:       0;  /* header and body have their own padding */
```

Internal structure:

```
┌──────────────────────────────────┐
│ Section Header (padding 20px 24px, border-bottom)
│ Section Body (padding 24px)
│ Section Footer (padding 16px 24px, border-top, optional)
└──────────────────────────────────┘
```

### KPI Card

Structure (in order, top to bottom):

```
Label    (13px, gray-600, font-medium)
Value    (28px, gray-900, font-semibold, tabular-nums)
Trend    (12px, success-700 / danger-700, with arrow icon)
```

Examples: Total Members, Total Savings, Outstanding Loans, Net Surplus, Members at Arrears.

Value formatting uses `<Money>` for amounts and `<Count>` for member counts.

---

## Forms

### Input Fields

```css
height:        40px;
border-radius: 12px;
border:        1px solid #D9D9D9;
padding:       0 12px;
font-size:     14px;
background:    #FFFFFF;
```

States:
- Default: as above
- Hover: `border: 1px solid #BDBDBD;`
- Focus: `border: 1px solid #3B82F6; box-shadow: var(--shadow-focus);`
- Disabled: `background: #F4F4F4; color: #767676; cursor: not-allowed;`
- Read-only: `background: #F8F8F8; border: 1px solid #EDEDED; color: #3D3D3D; cursor: default;`
- Error: `border: 1px solid #B91C1C; box-shadow: 0 0 0 3px rgba(185,28,28,.15);`
- Success: `border: 1px solid #157347;` (use sparingly, only after async validation passes)

### Labels

```css
font-size:    13px;
font-weight:  500;
color:        #5B5B5B;
margin-bottom: 6px;
display:      block;
```

Required indicator: `*` in `danger-700`, placed in the label after the field name. Never use placeholder text in lieu of a label.

```html
<label>Member Name <span class="text-danger-700">*</span></label>
```

### Help Text

```css
font-size:   12px;
color:       #767676;
margin-top:  6px;
```

Placed below the input. Replaced by the error message when validation fails.

### Field Errors

```css
font-size:   12px;
color:       #B91C1C;
margin-top:  6px;
display:     flex;
align-items: center;
gap:         4px;  /* for the warning icon */
```

Inline validation rules:
- Validate on **blur**, not on every keystroke
- Re-validate on submit
- Don't show errors while the user is still typing in a field
- Once an error has shown, validate on every change until cleared (so the user sees their fix)

### Read-Only Fields

Distinct from disabled. Read-only means "informational"; disabled implies "could be enabled."

```css
background: #F8F8F8;
border:     1px solid #EDEDED;
color:      #3D3D3D;
cursor:     default;
```

### Text Areas

```css
min-height:    96px;
border-radius: 12px;
padding:       12px;
resize:        vertical;
```

### Selects

Use shadcn `Select` component. Same height (40px) and radius (12px) as inputs.

### Date Pickers

Use `react-day-picker` via shadcn `Calendar` + `Popover`.
- Display format: `28 May 2026`
- Input also accepts typed dates in `DD/MM/YYYY` and `YYYY-MM-DD` formats
- Date range pickers: two inputs side-by-side, single calendar with two-month view

### Money Inputs

A specialized input for currency amounts.

- Right-aligned text
- Currency prefix inside the input on the left (small chip, e.g., `UGX`)
- Thousands separators inserted as the user types
- Decimal precision matches the currency (UGX: 0; KES: 2; USD: 2)
- Negative values disallowed by default (set `allowNegative` prop to enable)
- No browser spinner arrows (`appearance: none`)
- On blur, formats to canonical: `1234567` → `1,234,567.00`

### Percentage Inputs

- Right-aligned text
- `%` suffix inside the input on the right
- Max 2 decimal places
- Range typically 0–100, validated

### Multi-Step Forms

For loan applications, member onboarding, and similar long flows.

Stepper component at the top:

```
[1] Personal  →  [2] Employment  →  [3] Documents  →  [4] Review
 Done            Current             Upcoming         Upcoming
```

- Completed steps: `success-700` text, checkmark icon, clickable to revisit
- Current step: `primary-900` text, bold, filled circle
- Upcoming steps: `gray-500` text, hollow circle, not clickable
- Draft auto-save: every field change persists to a draft store; on session restore, prompt: "You have unsaved changes from {date}. Restore?"

### Form Section Headings

Used to group fields in long forms.

```css
font-size:      16px;
font-weight:    600;
color:          #1F1F1F;
padding-bottom: 8px;
border-bottom:  1px solid #EDEDED;
margin-bottom:  16px;
```

---

## Money & Number Display

Money is the most common visual element in this system. It is rendered through a single component.

### `<Money>` Component Contract

```tsx
<Money amount={1234567} currency="UGX" />
// Renders: UGX 1,234,567
```

**Rules:**

- Currency code prefix, space, then formatted amount (e.g., `UGX 1,234,567.00`, `KES 12,345.50`)
- Thousands separator: comma
- Decimal separator: period
- Decimal precision per currency:
  - UGX: 0 decimals
  - KES, TZS, RWF, USD, EUR, GBP: 2 decimals
  - Multi-currency platforms read precision from a currency registry
- Zero: `UGX 0` (not `—`, not `UGX -`)
- Negative: prefix minus sign in `danger-700`: `<span class="text-danger-700">-UGX 1,234</span>`
- Never use accounting parentheses for negatives (ambiguous to non-accountants)
- Always tabular-nums
- Right-aligned in table cells
- In KPI cards and headings, large variant (responsive size)

**Forbidden:**
- Inline string formatting like `${currency} ${amount.toLocaleString()}`
- Mixing precisions in the same column
- Hiding the currency code (it must always show, even in a single-currency tenant)

### `<Percentage>` Component Contract

```tsx
<Percentage value={12.5} />
// Renders: 12.50%
```

- Always 2 decimals
- `%` suffix
- Tabular-nums
- Right-aligned in tables

### `<Count>` Component Contract

```tsx
<Count value={1234} />
// Renders: 1,234
```

- Thousands separator: comma
- No decimals
- Tabular-nums

---

## Date & Time Display

All dates and times render through dedicated components. Raw `new Date().toString()` or `toLocaleString()` is forbidden in JSX.

### `<FormattedDate>` Component Contract

```tsx
<FormattedDate value="2026-05-28" />
// Renders: 28 May 2026
```

- Unambiguous: day, month name, four-digit year
- Never `MM/DD/YYYY` or `DD/MM/YYYY` in display (ambiguous)
- Used for: dates of birth, joining dates, due dates, period boundaries

### `<FormattedDateTime>` Component Contract

```tsx
<FormattedDateTime value="2026-05-28T14:32:00Z" />
// Renders: 28 May 2026, 14:32 (in tenant's timezone)
```

- 24-hour time
- Renders in the tenant's configured timezone
- Hover shows full ISO timestamp with timezone

### `<AuditTimestamp>` Component Contract

```tsx
<AuditTimestamp value="2026-05-28T14:32:07Z" />
// Renders: 28 May 2026, 14:32:07 EAT
```

- Includes seconds
- Always shows timezone abbreviation
- Used in audit logs, approval histories, system events

### `<RelativeTime>` Component Contract

```tsx
<RelativeTime value="2026-05-28T14:32:00Z" />
// Renders: 2 hours ago
```

- Used in feeds and recent-activity widgets only
- Hover shows the absolute timestamp
- Falls back to absolute date after 7 days

---

## Status Badges

Domain statuses across the system map to a small set of semantic styles. The `<StatusBadge>` component owns the mapping.

### Semantic Variants

```css
/* success — completed, positive end state */
background: #DCFCE7; color: #157347;

/* warning — pending action, intermediate */
background: #FEF3C7; color: #B45309;

/* danger — failed, rejected, arrears */
background: #FEE2E2; color: #B91C1C;

/* danger-solid — high-attention live state (in arrears, suspended) */
background: #B91C1C; color: #FFFFFF;

/* info — informational, in progress */
background: #DBEAFE; color: #1D4ED8;

/* neutral — draft, closed, archived */
background: #F4F4F4; color: #5B5B5B;

/* dark — terminal positive (closed-paid, completed) */
background: #1F1F1F; color: #FFFFFF;

/* accent — non-semantic emphasis (e.g., restructured) */
background: #EDE9FE; color: #5B21B6;
```

### Badge Specifications

```css
height:        24px;
border-radius: 8px;
padding:       0 8px;
font-size:     12px;
font-weight:   500;
display:       inline-flex;
align-items:   center;
gap:           4px;  /* if dot or icon */
```

Optional leading dot (6px circle) in the foreground color for higher recognition.

### Domain Status Mapping

#### Loan Status

| Status              | Variant       | Label                |
|---------------------|---------------|----------------------|
| draft               | neutral       | Draft                |
| submitted           | info          | Submitted            |
| under_review        | info          | Under Review         |
| approved            | success       | Approved             |
| disbursing          | warning       | Disbursing           |
| disbursed           | success       | Disbursed            |
| in_arrears          | danger-solid  | In Arrears           |
| restructured        | accent        | Restructured         |
| written_off         | danger        | Written Off          |
| closed              | dark          | Closed               |
| rejected            | danger        | Rejected             |
| withdrawn           | neutral       | Withdrawn            |
| cancelled           | neutral       | Cancelled            |

#### Member Status

| Status      | Variant      | Label       |
|-------------|--------------|-------------|
| prospect    | info         | Prospect    |
| active      | success      | Active      |
| dormant     | warning      | Dormant     |
| suspended   | danger-solid | Suspended   |
| exited      | neutral      | Exited      |
| deceased    | dark         | Deceased    |

#### Tenant Provisioning

| Status         | Variant      | Label          |
|----------------|--------------|----------------|
| pending        | info         | Pending        |
| provisioning   | warning      | Provisioning   |
| active         | success      | Active         |
| suspended      | danger-solid | Suspended      |
| failed         | danger       | Failed         |
| deprovisioning | warning      | Deprovisioning |
| archived       | neutral      | Archived       |

#### Fee Assessment

| Status          | Variant  | Label          |
|-----------------|----------|----------------|
| assessed        | warning  | Assessed       |
| partially_paid  | info     | Partially Paid |
| paid            | success  | Paid           |
| waived          | accent   | Waived         |
| cancelled       | neutral  | Cancelled      |

#### Approval Request

| Status            | Variant      | Label             |
|-------------------|--------------|-------------------|
| pending           | warning      | Pending Approval  |
| approved          | info         | Approved          |
| rejected          | danger       | Rejected          |
| executed          | success      | Executed          |
| execution_failed  | danger-solid | Execution Failed  |
| expired           | neutral      | Expired           |
| cancelled         | neutral      | Cancelled         |

#### Savings Account

| Status     | Variant      | Label      |
|------------|--------------|------------|
| active     | success      | Active     |
| dormant    | warning      | Dormant    |
| frozen     | danger-solid | Frozen     |
| closed     | neutral      | Closed     |

---

## Data Tables

Tables are the primary surface for financial data. They must be fast, dense, and accessible.

### Table Standards

```css
--height-table-header:      44px;
--height-table-row:         52px;   /* default density */
--height-table-row-compact: 40px;   /* compact density */
```

```css
Header background:  #F8F8F8;
Header text:        #5B5B5B, font-medium, 12px uppercase letter-spacing 0.04em;
Row border-bottom:  1px solid #EDEDED;
Row hover:          background #F8F8F8;
Row selected:       background #DBEAFE;
```

### Required Features

- Server-side pagination (cursor or offset)
- Server-side sorting (single column)
- Server-side filtering
- URL-synced state (filter values, sort column, page) via `nuqs`
- Column visibility toggle
- Density toggle (default ↔ compact), persisted per-user
- Export to CSV (server-rendered)
- Empty state
- Loading state (skeleton rows, not spinner)
- Error state
- Bulk selection (checkbox column, header checkbox selects page only — separate "select all matching" action)
- Row click navigates to detail (configurable)
- Sticky header on scroll
- Horizontal scroll for wide tables; first column may be sticky

### Column Conventions

- Money columns: right-aligned, tabular-nums, `<Money>` component
- Date columns: left-aligned, `<FormattedDate>`, fixed-width
- Status: center-aligned badges, fixed-width
- Actions: right-aligned, ghost icon buttons, fixed-width
- Member names, IDs: left-aligned, may truncate
- Numbers (counts, sequence): right-aligned, tabular-nums

### Truncation & Overflow

- Default cell behavior: single-line truncation with ellipsis
- Full value in `title` attribute and tooltip on hover
- Member names: max 32 characters, then truncate
- Narrations and descriptions: max 64 characters, then truncate
- Currency cells: never truncate; expand column
- Status badges: never truncate
- Long IDs (UUIDs): show first 8 + ellipsis + last 4, full value on hover

### Density Modes

Users toggle between **Default** (52px rows) and **Compact** (40px rows). Preference stored per user, applies across all tables.

In compact mode:
- Reduce vertical padding in cells
- Keep font sizes the same
- Reduce icon button sizes from 32px → 28px

---

## Empty States

Every list, table, and module must have an empty state.

Structure:

```
┌──────────────────────────────────┐
│         [Illustration / Icon]    │
│                                  │
│         Title (H4)               │
│         Description (Body)       │
│                                  │
│         [Primary Action]         │
└──────────────────────────────────┘
```

- Illustration: simple line icon from Lucide at 48px, gray-400
- Title: 18px, semibold, gray-900
- Description: 14px, gray-600, max 2 lines
- Action: primary button (omit if user has no permission to create)

Example:

```
No loan applications found.

Applications submitted by members
will appear here once they begin.

[New Application]
```

---

## Loading States

- **Skeleton loaders** for predictable layouts (tables, cards, profiles)
- **Inline spinner** (16px) for in-button loading
- **Progress bars** for known-duration operations (uploads, batch operations)
- **No full-page spinners.** Use skeletons or streaming server-rendered content instead

Skeletons:

```css
background: linear-gradient(90deg, #EDEDED 0%, #F4F4F4 50%, #EDEDED 100%);
background-size: 200% 100%;
animation: skeleton 1.4s ease-in-out infinite;
border-radius: 8px;
```

---

## Toasts, Alerts & Notifications

### Toasts

Use `sonner`. Bottom-right position.

- **Success** (5s): green check icon, success-700 text on light bg
- **Info** (5s): info icon, info-700 text
- **Warning** (8s): warning icon, warning-700 text
- **Error** (persistent until dismissed): danger icon, danger-700 text, includes "View details" or "Retry" action

Structure: title (bold, 14px) + optional description (13px, gray-700) + optional action button.

Never use toasts for critical warnings the user must acknowledge — use a modal or inline alert instead.

### Inline Alerts

Full-width banner above content. Used for record-level warnings.

```css
border-radius: 12px;
padding:       12px 16px;
border:        1px solid <semantic-200>;
background:    <semantic-50>;
color:         <semantic-900>;
display:       flex;
gap:           12px;
align-items:   start;
```

Variants: info, warning, danger, success. Each with semantic colors.

Examples:
- "This loan is in arrears. Last repayment was 45 days ago." (danger)
- "This member is dormant. Reactivate to perform transactions." (warning)
- "Pending approval: created by Sarah on 28 May 2026." (info)

### System Notifications (Notification Center)

Header bell icon with unread count. Click opens a panel listing recent notifications. Each notification:
- Icon (semantic)
- Title (14px, semibold)
- Description (13px, gray-700)
- Relative timestamp
- Link to the relevant record

---

## Permissions UX

Permissions affect rendering in three distinct ways. Use the right pattern.

### 1. User has permission → render normally

The button is visible and active. The screen loads with full data.

### 2. User lacks permission for an action → hide it

Do not show a disabled button. Operators will ask "why is this disabled?" and waste support time. If the user cannot perform the action, the button doesn't render at all.

```tsx
<PermissionGuard permission="loan.approve">
  <Button>Approve</Button>
</PermissionGuard>
```

### 3. User lacks permission to view a screen → explicit denial

Don't 404. Don't silently redirect. Render an explicit permission-denied state:

```
┌──────────────────────────────────┐
│       [Lock icon, 48px]          │
│                                  │
│   You don't have permission      │
│   to view this section.          │
│                                  │
│   Contact your administrator     │
│   if you believe this is wrong.  │
└──────────────────────────────────┘
```

### Maker-Checker Indicators

When a record has a pending approval request, the detail page shows a persistent banner above the record body:

```
⚠ Pending Approval
  Loan disbursement requested by Sarah Achieng on 28 May 2026.
  Requires 1 more approval before execution.
  [View Approval Request]
```

When an action button creates an approval request rather than executing, the confirm dialog says:

```
This will create an approval request, not execute the action.
Another authorized user must approve before the loan is disbursed.

[Cancel]  [Create Approval Request]
```

When viewing an executed record, the audit bar shows both maker and checker:

```
Created by Sarah Achieng · 28 May 2026
Approved by John Mukasa · 28 May 2026
Executed at 28 May 2026, 14:32:07 EAT
```

---

## Maker-Checker UX Patterns

The maker-checker workflow is one of the most distinctive operations in the system. Its UI is standardized.

### The Approval Inbox

A dedicated screen at `/approvals`, accessible from the header.

- Tabs: Pending (assigned to me) / Pending (all) / My Submissions / History
- Table columns: Operation Type, Subject, Amount, Requested By, Requested At, Quorum (e.g., `1 of 2`), Actions
- Filters: operation type, date range, requester
- Row click: opens approval detail in a side sheet
- Approval/rejection from the side sheet, with required comment field

### Approval Detail

When opened from the inbox or via a record link:

```
┌────────────────────────────────────────────┐
│ Approval Request                       [x] │
├────────────────────────────────────────────┤
│ Operation:   Loan Disbursement              │
│ Subject:     Loan #L-2026-001234            │
│ Amount:      UGX 5,000,000                  │
│                                             │
│ Requested by Sarah Achieng                  │
│ on 28 May 2026, 14:30 EAT                   │
│                                             │
│ Justification:                              │
│ "Loan approved by committee, disbursement   │
│  to member savings account."                │
│                                             │
│ Quorum: 1 of 2 approvers required           │
│ ────────────────────────────────────────    │
│                                             │
│ Actions performed:                          │
│ • Sarah Achieng requested at 14:30          │
│                                             │
│ Your comment:                               │
│ [textarea]                                  │
│                                             │
│ [Reject]                       [Approve]    │
└────────────────────────────────────────────┘
```

### Action Buttons That Trigger Approvals

When a button creates an approval request, label it explicitly:

- Instead of "Disburse Loan" → "Request Disbursement"
- Instead of "Reverse Transaction" → "Request Reversal"
- Instead of "Waive Fee" → "Request Waiver"

Combined with the confirm dialog described in the previous section, this makes the dual-state outcome unambiguous.

---

## Audit Bar

Every entity detail page (loan, member, savings account, etc.) shows an audit bar at the bottom or in a sidebar.

```
┌─ Activity ──────────────────────────────────┐
│                                              │
│ ● Modified by John Mukasa · 2 hours ago      │
│   Updated member phone number                │
│                                              │
│ ● Approved by Mary Akello · 5 hours ago      │
│   Approval request #AR-1234                  │
│                                              │
│ ● Created by Sarah Achieng · 28 May 2026    │
│                                              │
│ [View Full History]                          │
└──────────────────────────────────────────────┘
```

Shows the last 3 changes. Click "View Full History" opens a modal with paginated audit log entries scoped to this entity.

---

## Charts

Use Recharts. Tremor as a higher-level wrapper for dashboard primitives if useful.

### Preferred Chart Types

- **Line charts** for trends over time (savings growth, loan portfolio, members)
- **Area charts** for filled cumulative trends
- **Bar charts** for comparisons (collections by month, top borrowers)
- **Donut charts** for portfolio breakdowns (max 5 slices; everything else into "Other")

### Avoid

- 3D charts
- Pie charts with more than 5 slices
- Charts using more than 4 distinct colors
- Charts without axis labels
- Charts without tooltips on hover

### Chart Color Sequence

For multi-series charts, use this palette in order:

```css
1. #1F1F1F  (primary)
2. #3B82F6  (info)
3. #22C55E  (success)
4. #F59E0B  (warning)
5. #5B21B6  (accent)
6. #767676  (gray)
```

### Chart Spec

- Axis labels: 12px, gray-600
- Gridlines: 1px, gray-200, dashed
- Tooltip: white card with shadow-md, 14px text, tabular-nums for values
- Legend: bottom-aligned, 12px, gray-700
- Money values in tooltips: full `<Money>` formatting
- Empty state: explicit "Not enough data to render this chart" placeholder

---

## Icons

### Library

Lucide React. Never mix icon libraries.

```bash
pnpm add lucide-react
```

### Sizes

```css
xs: 14px;  /* inline with body text, dense tables */
sm: 16px;  /* default inline */
md: 20px;  /* button icons, form field icons */
lg: 24px;  /* nav items, prominent buttons */
xl: 32px;  /* page-level accents */
display: 48px; /* empty states, illustrations */
```

### Stroke Width

```css
stroke-width: 1.75;
```

Lucide's default 2 is slightly heavy; 1.75 reads as more refined in an enterprise context.

### Domain Icon Reference

| Domain         | Icon            |
|----------------|-----------------|
| Member         | `User`          |
| Group / SACCO  | `Users`         |
| Savings        | `Landmark`      |
| Shares         | `PieChart`      |
| Loan           | `Banknote`      |
| Application    | `FileText`      |
| Approval       | `CheckCircle2`  |
| Rejection      | `XCircle`       |
| Pending        | `Clock`         |
| Audit / History| `History`       |
| Settings       | `Settings`      |
| Notifications  | `Bell`          |
| Search         | `Search`        |
| Filter         | `Filter`        |
| Export         | `Download`      |
| Import         | `Upload`        |
| Edit           | `Pencil`        |
| Delete         | `Trash2`        |
| More / Menu    | `MoreHorizontal`|
| Add            | `Plus`          |
| Refresh        | `RefreshCw`     |
| Money / Payment| `Coins`         |
| Bank           | `Building2`     |
| Document       | `FileText`      |
| Calendar       | `Calendar`      |
| Lock           | `Lock`          |
| Logout         | `LogOut`        |

---

## Navigation Structure

### Sidebar Sections

```
Dashboard
  ├ Overview
  ├ Analytics
  └ Reports

Membership
  ├ Members
  ├ Groups
  ├ Shares
  └ Registrations

Savings
  ├ Accounts
  ├ Deposits
  ├ Withdrawals
  └ Interest

Loans
  ├ Products
  ├ Applications
  ├ Approvals
  ├ Disbursements
  ├ Repayments
  └ Arrears

Accounting
  ├ General Ledger
  ├ Journals
  ├ Trial Balance
  ├ Income Statement
  └ Balance Sheet

Treasury
  ├ Cashbook
  ├ Bank Accounts
  └ Reconciliation

Fees
  ├ Fee Types
  ├ Assessments
  └ Collections

Approvals          (badge with pending count)

Communication
  ├ SMS
  ├ Email
  ├ Notifications
  └ Templates

Reports
  ├ Regulatory
  ├ Portfolio
  └ Financial

Administration
  ├ Users
  ├ Roles
  ├ Permissions
  ├ Audit Logs
  └ Settings
```

### Sidebar Item Specification

```css
height:         40px;
padding:        0 16px;
border-radius:  10px;
font-size:      14px;
font-weight:    500;
color:          #5B5B5B;
display:        flex;
align-items:    center;
gap:            12px;
```

Active: `background: #F4F4F4; color: #1F1F1F;`
Hover: `background: #F8F8F8;`

Sidebar items conditionally render based on user permissions. Items the user can't access are hidden, not greyed out.

### Command Palette

Trigger: `Cmd+K` (Mac) / `Ctrl+K` (Windows/Linux).

Built with `cmdk`. Provides:
- Quick navigation to any screen
- Quick actions ("Create new member", "Record deposit")
- Recent records (last 10 viewed)
- Search by member name, loan ID, transaction reference

Power-user navigation. Every screen and major action is in the command palette.

---

## SACCO Domain Components

### Member Profile

Tabs (left-aligned within the profile, sticky on scroll):

```
Overview            (default tab)
Savings Accounts
Shares
Loans
Guarantor For
Transactions
Documents
Audit Trail
```

Header bar contains:
- Avatar (initials if no photo)
- Full name (H3) + member number
- Status badge
- Quick actions (right-aligned): Edit, Record Deposit, New Loan, More

### Savings Account View

Layout:

```
┌──────────────────────────────────────────────┐
│ Header: Account # · Member · Product · Status│
├──────────────────────────────────────────────┤
│ KPI Row:                                      │
│ Current Balance · Available · Interest YTD    │
├──────────────────────────────────────────────┤
│ Transaction Ledger (table, paginated)         │
│ Date · Type · Reference · Amount · Balance    │
├──────────────────────────────────────────────┤
│ Audit Bar                                     │
└──────────────────────────────────────────────┘
```

### Loan Detail View

Layout:

```
┌──────────────────────────────────────────────┐
│ Header: Loan # · Borrower · Product · Status  │
├──────────────────────────────────────────────┤
│ KPI Row:                                      │
│ Outstanding · Paid · Next Due · Days Past Due │
├──────────────────────────────────────────────┤
│ Tabs:                                         │
│ ├ Overview (terms, schedule, parties)         │
│ ├ Schedule (repayment schedule table)         │
│ ├ Repayments (history)                        │
│ ├ Guarantors (with savings locks)             │
│ ├ Collateral                                  │
│ ├ Approval History                            │
│ └ Audit Trail                                 │
└──────────────────────────────────────────────┘
```

If in arrears, a danger inline alert at the top: "This loan is in arrears. Days past due: 45. Outstanding: UGX 1,234,567."

---

## Dashboard Layout

### Row 1 — KPI Metrics

4–6 KPI cards in a responsive grid:

```
Total Members      Total Savings      Outstanding Loans      Net Surplus
Active Members     Savings Growth     Loan Portfolio         Members in Arrears
```

Each card: label, value (large, tabular-nums), trend indicator with percentage change.

### Row 2 — Charts

3 charts in a row:

```
Savings Growth (line)    Loan Portfolio (donut)    Collections Trend (bar)
```

### Row 3 — Operational Data

Two-column layout:

```
Recent Transactions (table, 10 rows)    │  Pending Approvals (list, 5 items)
                                         │
                                         │  Recent Loan Applications (list, 5)
```

---

## Print

Operations staff print statements, schedules, and reports. Print stylesheet is mandatory.

### Rules

- Black text on white background
- No sidebar, no header, no buttons, no nav
- Print-friendly font sizes (slightly larger than screen)
- Page breaks before major sections (`break-before: page`)
- Avoid splitting tables across pages (`break-inside: avoid` on rows)
- Include a print header on every page (logo, document title, page number)
- Include a footer with generation timestamp and the operator who printed

### Print-Specific Components

- `<PrintHeader>` — appears at top of every printed page
- `<PrintFooter>` — appears at bottom of every printed page
- `.print-only` — visible only when printing
- `.no-print` — hidden when printing

### Documents That Must Be Print-Ready

- Member statements (savings)
- Loan repayment schedules
- Loan statements
- Member account profile
- Trial balance
- Balance sheet
- Income statement
- General ledger account detail
- Audit log extracts

---

## Responsive Design

### Breakpoints

```css
sm:  640px;
md:  768px;
lg:  1024px;
xl:  1280px;
2xl: 1440px;
```

### Strategy

The portal is **desktop-first**. Operators work on laptops and external monitors.

- Below `lg` (1024px): sidebar collapses to icon-only, tables become horizontally scrollable, KPI cards stack vertically
- Below `md` (768px): the portal is functional but not optimized; show a banner suggesting a larger screen
- The portal is **not** a mobile experience. Mobile is a future, separate member-facing app

Some surfaces are mobile-friendly (approval inbox, notifications) so a manager can approve on-the-go. These are the exception, not the rule.

---

## Dark Mode

**Deferred to a future release.** Dark mode is properly specified or not specified at all; half-specified is worse than absent. Light-only ships in v1.

When dark mode lands, the following will be specified:
- Full neutral scale (independent from light scale, not just inverted)
- Adjusted semantic colors (the -500 stops re-tuned for dark backgrounds)
- Elevation via lighter surfaces, not shadows
- Border treatments at adjusted opacities

---

## Accessibility

### Requirements

- **WCAG AA compliance** for all colors, contrasts, and interactions
- **Keyboard navigation** for every interactive element
- **Visible focus states** via `:focus-visible`
- **Screen reader labels** on all icon buttons (`aria-label`)
- **Semantic HTML**: use `<button>`, `<nav>`, `<main>`, `<aside>`, `<table>`, etc., correctly
- **Form associations**: every input has a `<label for="">` or `aria-labelledby`
- **Error announcements**: form errors use `aria-live="polite"` and `aria-describedby`
- **Color is never the sole indicator**: status uses color + label, not color alone
- **Tab order is logical**: matches visual reading order
- **Skip links**: "Skip to content" at the top of every page

### Touch Targets

Minimum 40×40px for any interactive element. Even on desktop — mouse precision varies.

### Reduced Motion

Respect `prefers-reduced-motion: reduce` — disable non-essential animations and transitions.

---

## Internationalization

Even shipping in English-only for v1, the portal is i18n-ready from day one.

- All user-visible strings via `next-intl` `t()` calls
- No raw strings in JSX
- Plurals handled via ICU MessageFormat
- Dates, numbers, and currencies via locale-aware formatters (already handled by the `<Money>`, `<FormattedDate>` etc. components)
- RTL support: not required for English/Swahili but kept on the table by using logical CSS properties (`margin-inline-start` over `margin-left`) where convenient

Future locales (post-v1):
- English (en-UG, en-KE, en-TZ, en-RW)
- Swahili (sw)
- Luganda (lg) — long-term

---

## Design Tokens

All design values are exposed as CSS variables and consumed by Tailwind via a custom theme. The tokens live in `packages/ui/tokens.css`.

```css
:root {
  /* Colors — see Color System */
  /* Spacing — Tailwind defaults aligned to 8pt grid */
  /* Radius — see Border Radius */
  /* Shadows — see Shadows */
  /* Heights — see Component Heights */
  /* Motion — see Motion */
  /* Z-index */
  --z-base:       0;
  --z-dropdown:   1000;
  --z-sticky:     1020;
  --z-overlay:    1030;
  --z-modal:      1040;
  --z-popover:    1050;
  --z-toast:      1060;
  --z-tooltip:    1070;
}
```

---

## Recommended Technology Stack

### Framework

- **Next.js 15** (App Router)
- **React 19**
- **TypeScript** (strict mode, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`)

### UI

- **Tailwind CSS v4**
- **shadcn/ui** (owned components, copied into repo)
- **Radix UI primitives** (under shadcn)
- **Lucide React** (icons, stroke-width 1.75)

### State & Data

- **TanStack Query** (server state, caching, mutations)
- **Zustand** (small client state slices)
- **nuqs** (URL-synced state for tables and filters)

### Forms & Validation

- **React Hook Form**
- **Zod** (schemas shared with backend via `packages/schemas`)
- **@hookform/resolvers/zod**

### Tables & Charts

- **TanStack Table** (headless, server-side everything)
- **Recharts** (charts)
- **Tremor** (optional, dashboard primitives)

### Date & Time

- **date-fns**
- **react-day-picker** (via shadcn `Calendar`)

### Notifications & Commands

- **sonner** (toasts)
- **cmdk** (command palette)

### i18n

- **next-intl**

### Files & Uploads

- **react-dropzone**
- Presigned URLs to MinIO/S3

### Testing

- **Vitest**
- **React Testing Library**
- **Playwright** (E2E)
- **MSW** (API mocking)

### Tooling

- **pnpm** (package manager, workspaces)
- **Turborepo** (optional, build caching for monorepo)
- **ESLint** (with `react`, `tailwindcss`, `jsx-a11y` plugins)
- **Prettier**
- **Husky + lint-staged**

### Storybook

- **@storybook/nextjs** — every component documented, every state rendered, single source of truth alongside this document

---

## Design Keywords

```
Minimal
Enterprise
Financial
Trustworthy
Modern
Clean
Professional
Premium
Structured
Data-Focused
High Contrast
Scalable
Accessible
Calm
Dense
Fast
Operational
```

---

## Final Design Direction

The SACCO platform should feel like a modern financial SaaS product competing with:

- **Mambu** (cloud-native core banking)
- **Mercury** (clean enterprise banking UX)
- **Ramp** (data-dense fintech)
- **Modern Treasury** (treasury operations UI)
- **Tilled** (payments platform)

Every screen prioritizes operational efficiency, financial accuracy, and administrative productivity while maintaining a calm, monochrome-first visual language.

Reference points to **avoid**:
- 2010-era enterprise software (Oracle, SAP visual heritage)
- Over-colored consumer banking apps
- Marketing-heavy fintech landing-page aesthetic

---

## Living Documentation

This document is the **intent**. The **truth** is the Storybook at `apps/portal/storybook` plus the `packages/ui` component library.

Any change to a component, color token, or interaction pattern must update both:
1. This document (the design system spec)
2. Storybook (the executable reference)

PRs that change components without updating Storybook will be rejected in review. The two stay in sync.

---

## Change Log

### Version 2.0 (current)

- Added tabular numerals requirement and `font-tabular` token
- Added `<Money>`, `<Percentage>`, `<Count>` component contracts
- Added `<FormattedDate>`, `<FormattedDateTime>`, `<AuditTimestamp>`, `<RelativeTime>` contracts
- Expanded status badge system to cover all domain statuses with semantic mapping
- Added density modes (default vs compact)
- Added truncation and overflow rules
- Added dedicated Maker-Checker UX section
- Expanded Forms section (validation timing, required indicators, read-only, multi-step, money inputs, percentages)
- Added Permissions UX section (hide vs disable vs explicit denial)
- Added Color Contrast Matrix
- Added Focus States section
- Added Motion section (with prefers-reduced-motion)
- Added Print section
- Added Toasts, Alerts & Notifications section
- Added Icons section with domain reference table
- Standardized component heights to 40px
- Deferred dark mode to a future release
- Expanded recommended tech stack (nuqs, sonner, cmdk, date-fns, react-dropzone, Playwright, Vitest, MSW, Storybook)
- Replaced FLEXCUBE with Mercury, Ramp, Modern Treasury, Tilled in competitive references
- Added Design Tokens section with CSS variable layer
- Added Living Documentation policy

### Version 1.0

- Initial design system
