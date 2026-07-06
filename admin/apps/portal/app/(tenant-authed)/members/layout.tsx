import type { ReactNode } from "react";

// Parallel-route layout: `modal` is the @modal slot that intercepts /members/new
// (rendered over the list) while `children` is the list/detail content behind it.
export default function MembersLayout({
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
