export function parseRecords(result, dataType) {
  if (result.isError) throw new Error('Tool failed');
  const text = result.structuredContent?.result ?? result.content?.find(p => p.type === 'text')?.text;
  if (typeof text !== 'string' || !text.startsWith(`Records for ${dataType} from `)) throw new Error('Unexpected response');
  const separator = text.indexOf(': [');
  if (separator < 0) throw new Error('Missing records');
  const records = JSON.parse(text.slice(separator + 2));
  if (!Array.isArray(records) || !records.every(r => r && typeof r === 'object' && !Array.isArray(r))) throw new Error('Invalid records');
  return { records, truncated: text.slice(0, separator).includes('(showing the first ') };
}
