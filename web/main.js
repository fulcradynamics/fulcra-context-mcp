import { App } from '@modelcontextprotocol/ext-apps';
import { setupInvite } from './invite.js';
import { setupThreads } from './threads.js';
import { receiveEntrypoint } from './entrypoint.js';

const inlineList = document.querySelector('meta[name="mesh-presentation"]')?.content === 'threads';
const app = new App({ name: 'Fulcra Mesh', version: '0.1.0' }, { availableDisplayModes: inlineList ? ['inline', 'fullscreen'] : ['fullscreen', 'pip'] });
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
setupInvite(app, document.querySelector('#invite'), document.querySelector('#status')).then(connected => {
  applySafeArea(app.getHostContext());
  const status = document.querySelector('#mesh-status');
  if (connected) return setupThreads(app, document, entrypoint);
  status.textContent = 'Could not load threads: host connection failed. Reopen the app to retry.';
});
