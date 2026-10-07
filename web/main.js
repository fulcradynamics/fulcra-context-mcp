import { App } from '@modelcontextprotocol/ext-apps';
import { setupInvite } from './invite.js';

const app = new App({ name: 'AICQ', version: '0.1.0' }, { availableDisplayModes: ['fullscreen'] });
setupInvite(app, document.querySelector('#invite'), document.querySelector('#status'));
