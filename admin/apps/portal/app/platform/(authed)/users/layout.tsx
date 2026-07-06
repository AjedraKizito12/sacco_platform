import type { ReactNode } from "react";

// Parallel-route layout: the @modal slot intercepts the sibling /new route and
// renders it as a modal over the list; children is the list/detail behind it.
export default function SegmentLayout({
  children,
  modal,
}: {
  children: ReactNode;
  modal: ReactNode;
}) {
  return (
    <>
      {children}
      {modal}
    </>
  );
}
