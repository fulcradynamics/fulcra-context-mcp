import { App } from '@modelcontextprotocol/ext-apps';
import { setupInvite } from './invite.js';
import { loadMeshes } from './meshes.js';

const app = new App({ name: 'AICQ', version: '0.1.0' }, { availableDisplayModes: ['fullscreen'] });
setupInvite(app, document.querySelector('#invite'), document.querySelector('#status')).then(connected => {
  const status = document.querySelector('#mesh-status');
  if (connected) return loadMeshes(app, status, document.querySelector('#meshes'));
  status.textContent = 'Could not load mesh outboxes: host connection failed. Reopen the app to retry.';
});
