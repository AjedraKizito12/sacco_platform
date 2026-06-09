import type { FetchClient } from "../client";
import { platformAuth } from "./platformAuth";
import { tenants } from "./tenants";
import { billing } from "./billing";
import { members } from "./members";
import { savings } from "./savings";
import { credit } from "./credit";
import { fees } from "./fees";
import { ledger } from "./ledger";
import { reporting } from "./reporting";
import { makerChecker } from "./makerChecker";
import { impersonations } from "./impersonations";
import { audit } from "./audit";
import { admin } from "./admin";

export function buildResources(api: FetchClient) {
  return {
    platformAuth: platformAuth(api),
    tenants: tenants(api),
    billing: billing(api),
    members: members(api),
    savings: savings(api),
    credit: credit(api),
    fees: fees(api),
    ledger: ledger(api),
    reporting: reporting(api),
    makerChecker: makerChecker(api),
    impersonations: impersonations(api),
    audit: audit(api),
    admin: admin(api),
  } as const;
}

export type Resources = ReturnType<typeof buildResources>;
