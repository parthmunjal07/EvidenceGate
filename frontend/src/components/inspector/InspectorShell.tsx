import { useEffect, useRef, useState, type ReactNode } from "react";
import { ModalPortal } from "../common/ModalPortal";

export function Inspector({
  label,
  selected,
  placeholder,
  description,
  onClose,
  children,
  variant = "panel",
}: {
  label: string;
  selected: boolean;
  placeholder: string;
  description: string;
  onClose: () => void;
  children: ReactNode;
  variant?: "panel" | "modal";
}) {
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose);
  const [modal, setModal] = useState(
    () => window.matchMedia("(max-width: 1120px)").matches,
  );

  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 1120px)");
    const update = () => setModal(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!selected) return;
    const isDialog = modal || variant === "modal";
    const previousFocus = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    panel?.querySelector<HTMLElement>(".inspector-close")?.focus();
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
      if (!isDialog || event.key !== "Tab" || !panel) return;
      const focusable = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      previousFocus?.focus();
    };
  }, [selected, modal, variant]);

  useEffect(() => {
    document.body.classList.toggle("inspector-open", selected && (modal || variant === "modal"));
    return () => document.body.classList.remove("inspector-open");
  }, [selected, modal, variant]);

  const isDialog = selected && (modal || variant === "modal");
  const markup = (
    <>
      {selected && (modal || variant === "modal") && (
        <button
          type="button"
          className={`inspector-backdrop${variant === "modal" ? " inspector-modal-backdrop" : ""}`}
          aria-label="Close evidence inspector"
          onClick={onClose}
        />
      )}
      <aside
        ref={panelRef}
        className={`inspector${selected ? " has-selection is-open" : ""}${variant === "modal" ? " inspector-modal" : ""}`}
        aria-label={label}
        aria-modal={selected && (modal || variant === "modal") ? true : undefined}
        role={selected && (modal || variant === "modal") ? "dialog" : undefined}
      >
        {selected ? (
          children
        ) : (
          <div className="inspector-placeholder">
            <span className="inspect-glyph">⊕</span>
            <strong>{placeholder}</strong>
            <p>{description}</p>
          </div>
        )}
      </aside>
    </>
  );
  return isDialog
    ? <ModalPortal className={`inspector-layer${variant === "modal" ? " inspector-layer-centered" : " inspector-layer-drawer"}`}>{markup}</ModalPortal>
    : markup;
}

export function Header({
  kicker,
  title,
  subtitle,
  onClose,
  onBack,
  backLabel = "Back to family evidence",
}: {
  kicker: string;
  title: string;
  subtitle: string;
  onClose: () => void;
  onBack?: () => void;
  backLabel?: string;
}) {
  return (
    <div className="inspector-head">
      <div>
        {onBack && <button type="button" className="inspector-back-link" onClick={onBack}>← {backLabel}</button>}
        <p className="eyebrow">{kicker}</p>
        <h2>{title}</h2>
        <p className="inspector-subtitle">{subtitle}</p>
      </div>
      <button
        className="inspector-close"
        aria-label="Close inspector"
        onClick={onClose}
      >
        ×
      </button>
    </div>
  );
}
