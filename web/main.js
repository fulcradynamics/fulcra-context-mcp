import { App } from '@modelcontextprotocol/ext-apps';
import { setupInvite } from './invite.js';
import { loadMeshes } from './meshes.js';
import { setupMessages } from './messages.js';

const app = new App({ name: 'AICQ', version: '0.1.0' }, { availableDisplayModes: ['fullscreen'] });
const selectMesh = setupMessages(app, document);
setupInvite(app, document.querySelector('#invite'), document.querySelector('#status')).then(connected => {
  const status = document.querySelector('#mesh-status');
  if (connected) return loadMeshes(app, status, document.querySelector('#meshes'), selectMesh);
  status.textContent = 'Could not load threads: host connection failed. Reopen the app to retry.';
});
