import { type ReactNode, useEffect } from 'react'

// Minimal modal built on the native <dialog> element. Escape or the close button dismiss it.
export function Modal({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-backdrop">
      <dialog open className="modal" aria-label={title}>
        <div className="modal-head">
          <strong>{title}</strong>
          <button type="button" className="linklike" onClick={onClose}>
            close
          </button>
        </div>
        {children}
      </dialog>
    </div>
  )
}
