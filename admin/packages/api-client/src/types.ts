// admin/packages/api-client/src/types.ts
// Re-export the generated paths type as `Paths` so consumers don't need
// to know the codegen output's internal name.
import type { paths, components } from "./generated/schema";

export type Paths = paths;
export type Schemas = components["schemas"];
