# SACCO Admin Portal

This directory contains the Next.js 15 admin portal for the SACCO platform.
It's a self-contained pnpm + Turborepo monorepo; nothing here touches the
FastAPI backend code in `/app`.

## Layout

```
admin/
├── apps/
│   └── portal/        # Next.js 15 app (sub-plan 03)
└── packages/
    ├── tsconfig/       # Shared TS config
    ├── eslint-config/  # Shared ESLint config
    ├── ui/             # shadcn-based component library (sub-plan 04)
    ├── api-client/     # OpenAPI-generated client (sub-plan 05)
    └── schemas/        # Zod schemas mirrored from backend (sub-plan 06)
```

## Setup

```bash
nvm use     # picks up .nvmrc → Node 22
pnpm install
pnpm typecheck
pnpm lint
```

## Scripts

All Turborepo pipelines run from `admin/` and parallelise across packages:

- `pnpm dev` — start every dev server
- `pnpm build` — production build
- `pnpm typecheck` — TypeScript no-emit pass
- `pnpm lint` — ESLint across the workspace
- `pnpm test` — Vitest across the workspace

## Reference

- Portal v1 plan index: `../docs/superpowers/plans/2026-06-02-portal-v1-index.md`
- Design system spec: `../docs/sacco-design-system-v2.md`
- Design tokens (canonical): `../docs/tokens.css`
- Hard contracts: `../CLAUDE.md` § "Admin portal contracts"

## Git hooks

This workspace uses Husky 9 for pre-commit hooks. After cloning the
repo, point Git at the workspace's `.husky` directory once:

```bash
git config core.hooksPath admin/.husky
```

The `prepare` script (run automatically by `pnpm install`) takes care of
keeping the hooks executable.
