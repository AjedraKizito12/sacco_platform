"use client";

import { createContext, useContext, type ReactNode } from "react";
import { DEFAULT_CURRENCY, DEFAULT_TIMEZONE } from "../utils/currency";

export interface TenantCurrencyContextValue {
  currency: string;
  timeZone: string;
}

const TenantCurrencyContext = createContext<TenantCurrencyContextValue>({
  currency: DEFAULT_CURRENCY,
  timeZone: DEFAULT_TIMEZONE,
});

export interface TenantCurrencyProviderProps {
  currency?: string;
  timeZone?: string;
  children: ReactNode;
}

export function TenantCurrencyProvider({
  currency,
  timeZone,
  children,
}: TenantCurrencyProviderProps) {
  return (
    <TenantCurrencyContext.Provider
      value={{
        currency: currency ?? DEFAULT_CURRENCY,
        timeZone: timeZone ?? DEFAULT_TIMEZONE,
      }}
    >
      {children}
    </TenantCurrencyContext.Provider>
  );
}

export function useTenantCurrency(): TenantCurrencyContextValue {
  return useContext(TenantCurrencyContext);
}
