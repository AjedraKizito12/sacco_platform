# Product

## Register

product

## Users

SACCO platform operators (platform superusers/admins/finance/support), SACCO
staff (administrators, managers, accountants, tellers), and SACCO members.
Staff use the admin portal eight hours a day as an operational financial tool;
their mistakes cost money. Members use a lighter self-service portal to check
savings, shares, loans, and statements.

## Product Purpose

A multi-tenant SACCO (savings and credit cooperative) core banking platform.
The admin portal (Next.js, `admin/`) is a pure client of the FastAPI backend:
tenant management, billing, members, savings, credit, ledger, approvals,
audit, notifications. Success means operators complete high-volume financial
workflows quickly and without errors, and every sensitive action is auditable.

## Brand Personality

Premium, professional, data-focused. Trustworthy, calm, precise. Approachable
without being playful; the interface recedes so the data reads first.

## Anti-references

- Consumer-fintech gradient flash: no gradients, glassmorphism, or decorative
  color. Monochrome-first; color is a signal, not decoration.
- Marketing-site whitespace: this is a dense operational tool, not a landing
  page. Whitespace serves data.
- Anything that hides state: silent failures, optimistic UI without
  confirmation, unlabeled icons.

## Design Principles

1. Clarity over decoration: numbers, statuses, and balances are the product.
2. Consistency everywhere: a component behaves identically in every module.
3. Data first: density is a feature; whitespace serves data.
4. Error prevention over error recovery: confirm dialogs, read-only fields,
   maker-checker flows; assume the user is tired and the data is sensitive.
5. Speed is a feature: server-side pagination, keyboard access, fast loads.

## Accessibility & Inclusion

WCAG AA. Every component keyboard-accessible. Tabular numerals for all
figures. Full contract detail lives in `docs/sacco-design-system-v2.md`
(canonical design system) and the portal contracts in `CLAUDE.md`.
