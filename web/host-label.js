// Friendly display names for known hosts; unknown hosts keep their raw name.
const HOST_LABELS = { chatgpt: 'ChatGPT' };
export const hostLabel = raw => raw ? (HOST_LABELS[raw.toLowerCase()] ?? raw) : raw;
export const hostName = app => hostLabel(app.getHostVersion()?.name) || 'your agent';
