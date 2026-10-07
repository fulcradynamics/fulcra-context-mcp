const prefix = 'Available data types, grouped by compatible tool: ';

export function parseMeshes(result) {
  if (result.isError) throw new Error('Tool failed');
  const text = result.structuredContent?.result ?? result.content?.find(p => p.type === 'text')?.text;
  if (typeof text !== 'string' || !text.startsWith(prefix)) throw new Error('Unexpected result');
  const catalog = JSON.parse(text.slice(prefix.length));
  if (!catalog || Array.isArray(catalog) || typeof catalog !== 'object'
    || !Object.values(catalog).every(Array.isArray)) throw new Error('Invalid catalog');
  const entries = Object.entries(catalog)
    .filter(([group]) => group.startsWith('data types usable with: ') && group.slice('data types usable with: '.length).split(' | ').includes('get_records'))
    .flatMap(([, entries]) => entries);
  if (!entries.every(e => e && typeof e.id === 'string' && typeof e.name === 'string'
    && (e.fulcra_userid === undefined || typeof e.fulcra_userid === 'string'))) throw new Error('Invalid entry');
  return [...new Map(entries
    .filter(e => e.id.startsWith('MomentAnnotation/') && /\bmesh outbox\b/i.test(e.name))
    .map(e => [JSON.stringify([e.fulcra_userid ?? '', e.id]), e])).values()]
    .sort((a, b) => a.name.localeCompare(b.name));
}

export async function loadMeshes(app, status, list, onSelect) {
  status.textContent = 'Loading mesh outboxes — calling get_data_catalog…';
  list.replaceChildren();
  try {
    const result = await app.callServerTool({
      name: 'get_data_catalog', arguments: { name: 'Mesh Outbox' },
    }, { timeout: 30000 });
    const meshes = parseMeshes(result);
    for (const mesh of meshes) {
      const row = list.ownerDocument.createElement('li');
      const button = list.ownerDocument.createElement('button');
      button.type = 'button';
      button.textContent = mesh.name;
      button.addEventListener('click', () => onSelect(mesh));
      row.append(button, ` — ${mesh.fulcra_userid ? `Owner: ${mesh.fulcra_userid}` : 'Your outbox'} — ${mesh.id}`);
      list.append(row);
    }
    status.textContent = `get_data_catalog completed — ${meshes.length} mesh outbox${meshes.length === 1 ? '' : 'es'} returned.`;
  } catch {
    list.replaceChildren();
    status.textContent = 'Could not load mesh outboxes (get_data_catalog failed or returned an invalid result). Reopen the app to retry.';
  }
}
