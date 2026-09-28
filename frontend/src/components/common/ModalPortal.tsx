import type { ReactNode } from "react";
import { createPortal } from "react-dom";

export function ModalPortal({
  children,
  className,
}: {
  children: ReactNode;
  className: string;
}) {
  return createPortal(
    <div className={className}>{children}</div>,
    document.body,
  );
}
