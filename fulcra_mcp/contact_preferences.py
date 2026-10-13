"""Authenticated contact policy, separate from notification checkpoints."""
import json
import re
from threading import RLock

ROOT = '/agent/chatgpt/contact-preferences'
PATH = ROOT + '/settings.md'
LOCK = RLock()  # Serializes this worker only; storage has no compare-and-swap.
DEFAULTS = dict(autonomous_replies=False, status_metadata=False,
                attention_waiting=True, attention_overdue=True, unanswered_days=2,
                attention_high_priority=True, notifications='attention', special_instructions='')
SCHEMA = {
    'autonomous_replies': {'type': 'boolean', 'title': 'Allow autonomous replies',
        'description': 'Opt in to bounded replies using known, authorized information. Existing task restrictions still apply; no commitments or unrelated actions.'},
    'status_metadata': {'type': 'boolean', 'title': 'Save contact status',
        'description': 'Allow neutral, peer-visible status labels on your own connections. Existing task restrictions still apply.'},
    'attention_waiting': {'type': 'boolean', 'title': 'Flag contacts waiting for you'},
    'attention_overdue': {'type': 'boolean', 'title': 'Flag contacts that have not replied'},
    'unanswered_days': {'type': 'integer', 'title': 'Days without a response', 'minimum': 1, 'maximum': 365},
    'attention_high_priority': {'type': 'boolean', 'title': 'Flag high-priority messages'},
    'notifications': {'type': 'string', 'title': 'Notify about', 'enum': ['attention', 'all_messages', 'none'],
        'description': 'Guides check summaries, not ChatGPT completion alerts or OS permissions.'},
    'special_instructions': {'type': 'string', 'title': 'Special instructions', 'maxLength': 2000,
        'description': 'Additional checking guidance; cannot grant reply, sharing or action permission.'},
}


def validate(values):
    if not isinstance(values, dict) or values.keys() - DEFAULTS.keys():
        raise ValueError('Unknown contact preference.')
    for key, value in values.items():
        schema = SCHEMA[key]
        expected = {'boolean': bool, 'integer': int, 'string': str}[schema['type']]
        if type(value) is not expected:
            raise ValueError('Invalid preference type: ' + key)
        if 'enum' in schema and value not in schema['enum']:
            raise ValueError('Invalid preference choice: ' + key)
        if 'minimum' in schema and not schema['minimum'] <= value <= schema['maximum']:
            raise ValueError('Invalid preference range: ' + key)
        if 'maxLength' in schema and len(value) > schema['maxLength']:
            raise ValueError('Special instructions are too long.')
    return values


def private_account(api):
    account = api.get_fulcra_userid()
    if not isinstance(account, str) or not account:
        raise ValueError('Missing authenticated account.')
    shares = api.get_datashares()
    if not isinstance(shares, list):
        raise ValueError('Could not establish preference privacy.')
    for share in shares:
        if type(share.get('share_all_data')) is not bool or share['share_all_data']:
            raise ValueError('Preferences may be shared; repair privacy first.')
        from .tools import _split_share_types
        selectors = share.get('fulcra_data_types', [])
        if not isinstance(selectors, list) or any(not isinstance(s, str) for s in selectors):
            raise ValueError('Could not establish preference privacy.')
        files, history, _ = _split_share_types(selectors)
        for field, encoded in (('file_paths', files), ('file_history_paths', history)):
            paths = share.get(field, [])
            if not isinstance(paths, list):
                raise ValueError('Could not establish preference privacy.')
            for path in paths + encoded:
                if not isinstance(path, str) or not path or '*' in path:
                    raise ValueError('Could not establish preference privacy.')
                path = '/' + path.lstrip('/')
                if PATH == path or PATH.startswith(path.rstrip('/') + '/'):
                    raise ValueError('Preferences may be shared; repair privacy first.')
        if share.get('files'):
            raise ValueError('Could not establish preference privacy.')
    return account


def load(api):
    account = private_account(api)
    listing = api.list_files(ROOT)
    matches = [f for f in listing['files'] if f['name'] == 'settings.md']
    if not matches:
        return dict(version=1, account_id=account, preferences={})
    if len(matches) != 1:
        raise ValueError('Ambiguous preferences.')
    with api.download_file(matches[0]['id']) as response:
        content = response.read(32001)
    if len(content) > 32000:
        raise ValueError('Preferences exceed read limit.')
    blocks = re.findall(r'^```json\s*\n(.*?)^```\s*$', content.decode(), re.M | re.S)
    if len(blocks) != 1:
        raise ValueError('Invalid preferences.')
    document = json.loads(blocks[0])
    if (type(document.get('version')) is not int or document['version'] != 1
            or document.get('account_id') != account):
        raise ValueError('Invalid preference identity.')
    validate(document['preferences'])
    return document


def read(api):
    return {**DEFAULTS, **load(api)['preferences']}


def update(api, changes):
    validate(changes)
    if not changes:
        raise ValueError('Choose at least one preference.')
    with LOCK:
        document = load(api)
        document['preferences'] = {**document['preferences'], **changes}
        if private_account(api) != document['account_id']:
            raise ValueError('Authenticated account changed.')
        payload = ('---\ntype: Settings\ntitle: Contact preferences\n---\n\n```json\n'
                   + json.dumps(document, ensure_ascii=False, indent=2) + '\n```\n').encode()
        api.upload_file(payload, 'text/markdown', len(payload), PATH)
        current = load(api)
        if current != document:
            raise ValueError('Preference save not verified; reload before retrying.')
        return {**DEFAULTS, **current['preferences']}


TOKEN = '[contact_preferences:'
PATTERN = re.compile(r'^\[contact_preferences: (\{[^\r\n]*\})\]$', re.M)


def parse_overrides(description):
    if not isinstance(description, str):
        raise ValueError('Missing connection description.')
    if TOKEN not in description:
        return {}
    match = PATTERN.search(description)
    if description.count(TOKEN) != 1 or not match:
        raise ValueError('Malformed contact preferences; do not infer permission.')
    return validate(json.loads(match[1]))


def write_overrides(description, overrides):
    validate(overrides)
    parse_overrides(description)
    marker = '[contact_preferences: ' + json.dumps(overrides, separators=(',', ':')) + ']'
    match = PATTERN.search(description)
    if match:
        return description[:match.start()] + marker + description[match.end():]
    from .mesh_identifier import _marker
    label = _marker(description)
    index = label[0] if label else len(description)
    before = description[:index]
    return before + ('' if before.endswith('\n') else '\n') + marker + ('\n' if label else '') + description[index:]


def effective(global_values, overrides):
    validate(global_values)
    validate(overrides)
    result = {**global_values, **overrides}
    # Owned overrides may restrict, never elevate, the global opt-in switches.
    for key in ('autonomous_replies', 'status_metadata'):
        result[key] = global_values[key] and overrides.get(key, True)
    return result
