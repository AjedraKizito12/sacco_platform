"use client";

import { AppearanceSection } from "@/components/theme/AppearanceSection";

/**
 * Thin member-profile wrapper around the shared `AppearanceSection` body.
 * Kept as its own file so the profile page composes it the same way it
 * composes `MemberKycSection`.
 */
export function MemberAppearanceSection() {
  return <AppearanceSection />;
}
