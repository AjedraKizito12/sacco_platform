import type { FetchClient } from "../client";
import { platformAuth } from "./platformAuth";
import { tenants } from "./tenants";
import { billing } from "./billing";
import { members } from "./members";
import { savings } from "./savings";
import { shares } from "./shares";
import { credit } from "./credit";
import { fees } from "./fees";
import { ledger } from "./ledger";
import { reporting } from "./reporting";
import { makerChecker } from "./makerChecker";
import { impersonations } from "./impersonations";
import { audit } from "./audit";
import { keys } from "./keys";
import { admin } from "./admin";
import { dashboard } from "./dashboard";
import { member } from "./member";
import { memberAuth } from "./memberAuth";

export function buildResources(api: FetchClient) {
  return {
    platformAuth: platformAuth(api),
    tenants: tenants(api),
    billing: billing(api),
    members: members(api),
    savings: savings(api),
    shares: shares(api),
    credit: credit(api),
    fees: fees(api),
    ledger: ledger(api),
    reporting: reporting(api),
    makerChecker: makerChecker(api),
    impersonations: impersonations(api),
    audit: audit(api),
    keys: keys(api),
    admin: admin(api),
    dashboard: dashboard(api),
    member: member(api),
    memberAuth: memberAuth(api),
  } as const;
}

export type Resources = ReturnType<typeof buildResources>;
