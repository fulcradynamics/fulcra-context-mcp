import { icon, X } from './icons.js';
import { hostLabel } from './chat-only.js';

// A small vanilla toast, in the spirit of Sonner (the emil-design-eng skill):
// good defaults, CSS transitions (not keyframes) so stacking/removal stay smooth,
// dismissable, auto-timeout that pauses on hover. No dependency, sandbox-safe.
const AUTODISMISS_MS = 10000;

// options: a string (description only) or { title, description, action: {label,
// onClick}, duration }. duration 0 keeps it up until dismissed. Returns dismiss().
export function showToast(doc, options) {
  const { title, description, action, duration = AUTODISMISS_MS } =
    typeof options === 'string' ? { description: options } : options;
  let container = doc.querySelector('.toaster');
  if (!container) {
    container = doc.createElement('div');
    container.className = 'toaster';
    container.setAttribute('aria-live', 'polite');
    doc.body.append(container);
  }
  const toast = doc.createElement('div'); toast.className = 'toast'; toast.setAttribute('role', 'status');
  const body = doc.createElement('div'); body.className = 'toast-body';
  if (title) { const t = doc.createElement('p'); t.className = 'toast-title'; t.textContent = title; body.append(t); }
  if (description) { const d = doc.createElement('p'); d.className = 'toast-text'; d.textContent = description; body.append(d); }
  toast.append(body);

  let timer;
  const dismiss = () => {
    clearTimeout(timer);
    toast.classList.remove('toast-shown');
    toast.addEventListener('transitionend', () => toast.remove(), { once: true });
  };
  if (action) {
    const act = doc.createElement('button'); act.type = 'button'; act.className = 'toast-action'; act.textContent = action.label;
    act.addEventListener('click', () => { try { action.onClick?.(); } finally { dismiss(); } });
    toast.append(act);
  }
  const close = doc.createElement('button'); close.type = 'button'; close.className = 'toast-close';
  close.setAttribute('aria-label', 'Dismiss'); close.append(icon(X, 'btn-icon', 15));
  close.addEventListener('click', dismiss);
  toast.append(close);
  container.append(toast);
  // Transition in from the next frame (transition, not keyframes, so it never
  // restarts mid-stack).
  requestAnimationFrame(() => toast.classList.add('toast-shown'));

  // Auto-dismiss (unless duration 0), paused while hovered.
  const arm = () => { if (duration) timer = setTimeout(dismiss, duration); };
  toast.addEventListener('pointerenter', () => clearTimeout(timer));
  toast.addEventListener('pointerleave', arm);
  arm();
  return dismiss;
}

// Full-panel handoffs continue in the host conversation.
export function continueMessage(app) {
  const host = hostLabel(app.getHostVersion()?.name);
  return `Open ${host ? `your ${host} chat` : 'your chat'} to continue.`;
}

// Show a spinner inside a button and disable it while an async action runs;
// returns a restore function. The spinner leads the label so a right-anchored
// button keeps its label in place (no jump) as it widens.
export function spinButton(button) {
  button.disabled = true;
  const spinner = button.ownerDocument.createElement('span');
  spinner.className = 'refresh-spinner btn-spinner'; spinner.setAttribute('aria-hidden', 'true');
  button.prepend(spinner);
  return () => { spinner.remove(); button.disabled = false; };
}
