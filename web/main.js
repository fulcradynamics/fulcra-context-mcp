import { App } from '@modelcontextprotocol/ext-apps';
import { setupInvite } from './invite.js';
import { setupThreads } from './threads.js';
import { receiveEntrypoint } from './entrypoint.js';
import { icon, UserPlus } from './icons.js';
import { setupCheckStatus } from './check-status.js';

const inlineList = document.querySelector('meta[name="connection-presentation"]')?.content === 'threads';
const app = new App({ name: 'Agents I Know', version: '0.1.0' }, { availableDisplayModes: inlineList ? ['inline', 'fullscreen'] : ['fullscreen', 'pip'] });
if (inlineList) document.documentElement.classList.add('compact-threads');
// SDK 1.7.5: safeAreaInsets are optional pixel values, not host composer height.
function applySafeArea(context) {
  if (!context?.safeAreaInsets) return;
  for (const side of ['top', 'right', 'bottom', 'left']) {
    document.documentElement.style.setProperty(`--host-safe-${side}`, `${Math.max(0, context.safeAreaInsets[side])}px`);
  }
}
app.addEventListener('hostcontextchanged', applySafeArea);
const entrypoint = receiveEntrypoint(app, document); // Before setupInvite connects.
const inviteButtons = [...document.querySelectorAll('#invite, #invite-empty')];
for (const button of inviteButtons) button.prepend(icon(UserPlus, 'btn-icon'));
setupInvite(app, inviteButtons, document.querySelector('#status')).then(connected => {
  applySafeArea(app.getHostContext());
  const status = document.querySelector('#connection-status');
  if (!connected) {
    status.textContent = 'Could not load Agent Contacts: host connection failed. Reopen the app to retry.';
    return;
  }
  setupCheckStatus(app, document, Boolean(app.getHostCapabilities()?.message?.text));
  return setupThreads(app, document, entrypoint);
});
