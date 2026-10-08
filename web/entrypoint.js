// Presentation is fixed by the server's resource, never inferred from fullscreen
// or from account/message content. SDK 1.7.5 tool-result carries structuredContent;
// hostContext.toolInfo is optional and is not an initial tool result.
export function receiveEntrypoint(app, doc) {
  const presentation = doc.querySelector('meta[name="mesh-presentation"]')?.content === 'thread' ? 'thread' : 'global';
  let deliver, first, received = false;
  app.ontoolresult = result => {
    if (received) return;
    received = true;
    first = result;
    deliver?.(result);
  };
  app.ontoolcancelled = () => app.ontoolresult({ isError: true });
  return { presentation, consume(callback) {
    deliver = callback;
    if (received) callback(first);
  } };
}
