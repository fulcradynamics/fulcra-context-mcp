import protocol from '../fulcra_mcp/static/connection-schema.json' with { type: 'json' };

// Compare protocol constraints, not descriptive schema metadata or key order.
function semantic(value, key) {
  if (Array.isArray(value)) return ['enum', 'required', 'required_fields'].includes(key) ? [...value].sort() : value.map(v => semantic(v));
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort()
    .filter(k => !['description', 'title', 'default'].includes(k)).map(k => [k, semantic(value[k], k)]));
  return value;
}
export function compatibleSchema(entry) {
  return JSON.stringify(semantic({fields: Object.fromEntries(Object.keys(protocol.fields).map(k => [k, entry.fields?.[k]])),
    required_fields: entry.required_fields})) === JSON.stringify(semantic(protocol));
}
