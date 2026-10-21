import { App } from '@modelcontextprotocol/ext-apps';
import { setupInvite } from './invite.js';
import { setupThreads } from './threads.js';
import { receiveEntrypoint } from './entrypoint.js';
import { icon, UserPlus, Link } from './icons.js';
import { setupCheckStatus } from './check-status.js';
import { showToast, continueMessage } from './toast.js';
import { hostLabel } from './host-label.js';

const app = new App({ name: 'Agents I Know', version: '0.1.0' }, { availableDisplayModes: ['fullscreen'] });
// SDK 1.7.5: safeAreaInsets are optional pixel values, not host composer height.
function applySafeArea(context) {
  if (context?.displayMode) document.documentElement.dataset.displayMode = context.displayMode;
  if (!context?.safeAreaInsets) return;
  for (const side of ['top', 'right', 'bottom', 'left']) {
    document.documentElement.style.setProperty(`--host-safe-${side}`, `${Math.max(0, context.safeAreaInsets[side])}px`);
  }
}
app.addEventListener('hostcontextchanged', applySafeArea);
// A chat handoff shows a spinner on the button, then a "Request sent to <host>"
// toast — the global toast persists (guidance) while the inline one auto-dismisses.
const notifySent = description => {
  const host = hostLabel(app.getHostVersion()?.name);
  return showToast(document, {
    title: host ? `Request sent to ${host}` : 'Request sent',
    description,
  });
};
const entrypoint = receiveEntrypoint(app, document); // Before setupInvite connects.
const inviteButtons = [...document.querySelectorAll('#invite, #invite-welcome')];
for (const button of inviteButtons) button.prepend(icon(UserPlus, 'btn-icon'));
const openInviteButtons = [...document.querySelectorAll('#open-invite, #open-invite-welcome')];
for (const button of openInviteButtons) button.prepend(icon(Link, 'btn-icon'));
setupInvite(app, inviteButtons, document.querySelector('#status'), { notifySent }, openInviteButtons).then(connected => {
  applySafeArea(app.getHostContext());
  const status = document.querySelector('#connection-status');
  if (!connected) {
    status.textContent = 'Could not load Agent Contacts: host connection failed. Reopen the app to retry.';
    return;
  }
  setupCheckStatus(app, document, Boolean(app.getHostCapabilities()?.message?.text), continueMessage(app), notifySent);
  return setupThreads(app, document, entrypoint);
});
