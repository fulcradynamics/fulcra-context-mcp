import { App } from '@modelcontextprotocol/ext-apps';
import { setupInvite } from './invite.js';
import { loadMeshes } from './meshes.js';
import { setupMessages } from './messages.js';

const app = new App({ name: 'Fulcra Mesh', version: '0.1.0' }, { availableDisplayModes: ['fullscreen'] });
// SDK 1.7.5: safeAreaInsets are optional pixel values, not host composer height.
function applySafeArea(context) {
  if (!context?.safeAreaInsets) return;
  for (const side of ['top', 'right', 'bottom', 'left']) {
    document.documentElement.style.setProperty(`--host-safe-${side}`, `${Math.max(0, context.safeAreaInsets[side])}px`);
  }
}
app.addEventListener('hostcontextchanged', applySafeArea);
const selectMesh = setupMessages(app, document);
setupInvite(app, document.querySelector('#invite'), document.querySelector('#status')).then(connected => {
  applySafeArea(app.getHostContext());
  const status = document.querySelector('#mesh-status');
  if (connected) return loadMeshes(app, status, document.querySelector('#meshes'), selectMesh);
  status.textContent = 'Could not load threads: host connection failed. Reopen the app to retry.';
});
