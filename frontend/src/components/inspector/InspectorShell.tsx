import { useEffect, useRef, useState, type ReactNode } from "react";

export function Inspector({
  label,
  selected,
  placeholder,
  description,
  onClose,
  children,
}: {
  label: string;
  selected: boolean;
  placeholder: string;
  description: string;
  onClose: () => void;
  children: ReactNode;
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
    const previousFocus = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    panel?.querySelector<HTMLElement>(".inspector-close")?.focus();
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
      if (!modal || event.key !== "Tab" || !panel) return;
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
  }, [selected, modal]);

  useEffect(() => {
    document.body.classList.toggle("inspector-open", selected && modal);
    return () => document.body.classList.remove("inspector-open");
  }, [selected, modal]);

  return (
    <>
      {selected && modal && (
        <button
          type="button"
          className="inspector-backdrop"
          aria-label="Close evidence inspector"
          onClick={onClose}
        />
      )}
      <aside
        ref={panelRef}
        className={`inspector${selected ? " has-selection is-open" : ""}`}
        aria-label={label}
        aria-modal={selected && modal ? true : undefined}
        role={selected && modal ? "dialog" : undefined}
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
}

export function Header({
  kicker,
  title,
  subtitle,
  onClose,
}: {
  kicker: string;
  title: string;
  subtitle: string;
  onClose: () => void;
}) {
  return (
    <div className="inspector-head">
      <div>
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
