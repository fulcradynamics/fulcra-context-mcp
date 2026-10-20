// Presentation is fixed by the server's resource, never inferred from fullscreen
// or from account/message content. SDK 1.7.5 tool-result carries structuredContent;
// hostContext.toolInfo is optional and is not an initial tool result.
export function receiveEntrypoint(app, doc) {
  const marker = doc.querySelector('meta[name="connection-presentation"]')?.content;
  const presentation = marker === 'thread' ? marker : 'global';
  // Server-owned direct-resource variant, not a host capability or timeout guess.
  const directResource = presentation === 'thread'
    && doc.querySelector('meta[name="connection-startup"]')?.content === 'resource';
  let deliver, first, received = false;
  app.ontoolresult = result => {
    if (received) return;
    received = true;
    first = result;
    deliver?.(result);
  };
  app.ontoolcancelled = () => app.ontoolresult({ isError: true });
  return { presentation, directResource, consume(callback) {
    deliver = callback;
    if (received) callback(first);
  }, dispose() {
    received = true;
    first = undefined;
    deliver = undefined;
  } };
}
