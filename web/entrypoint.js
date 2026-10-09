// Presentation is fixed by the server's resource, never inferred from fullscreen
// or from account/message content. SDK 1.7.5 tool-result carries structuredContent;
// hostContext.toolInfo is optional and is not an initial tool result.
export function receiveEntrypoint(app, doc) {
  const marker = doc.querySelector('meta[name="mesh-presentation"]')?.content;
  const presentation = ['thread', 'threads'].includes(marker) ? marker : 'global';
  // Server-owned direct-resource variant, not a host capability or timeout guess.
  const directResource = presentation === 'threads'
    && doc.querySelector('meta[name="mesh-startup"]')?.content === 'resource';
  let deliver, first, received = false;
  app.ontoolresult = result => {
    if (received) return;
    received = true;
    first = result;
    deliver?.(result);
  };
  app.ontoolcancelled = () => app.ontoolresult({ isError: true });
  let hostChanges = {}, hostListener;
  const onHost = context => {
    hostChanges = { ...hostChanges, ...context };
    hostListener?.(context);
  };
  app.addEventListener('hostcontextchanged', onHost);
  return { presentation, directResource, observeHost(callback) {
    hostListener = callback;
    callback({ ...app.getHostContext(), ...hostChanges });
    return () => { hostListener = undefined; app.removeEventListener('hostcontextchanged', onHost); };
  }, consume(callback) {
    deliver = callback;
    if (received) callback(first);
  } };
}
