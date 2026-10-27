"""Contact preferences stored in one owned Event data type's description.

The description holds a JSON document: global values plus per-connection
overrides keyed by ``<own Event connection>|<peer user ID>``. Values are user
configuration, not instructions.
"""
import json
import re
from threading import RLock

NAME = 'Fulcra Contact Preferences'
LOCK = RLock()  # Serializes this worker only; storage has no compare-and-swap.
DEFAULTS = dict(acknowledge_messages=True, share_contact_status=True, pause_autonomous_replies=False,
                attention_waiting=True, attention_overdue=True, unanswered_days=2,
                attention_high_priority=True, attention_peer_membership_announcements=True,
                attention_new_unmatched_contact=True, attention_new_matched_contact=True,
                notifications='attention', checking_preferences='')
# Native settings only support string enums, not separate option labels.
NOTIFICATION_LABELS = dict(attention='only surfaced activity',
                          all_messages='all messages from my contacts',
                          none='no notifications or emails')
# Native settings fields; checking_preferences is set by chatting with the agent.
SCHEMA = {
    'acknowledge_messages': {'type': 'boolean', 'title': 'Acknowledge messages',
        'description': 'Send read receipts for messages your agent reports to you.'},
    'share_contact_status': {'type': 'boolean', 'title': 'Share contact status',
        'description': 'Save a general status of each conversation, such as a priority message '
                       'or time since the last reply, on your contact. Your contact can see it.'},
    'pause_autonomous_replies': {'type': 'boolean', 'title': 'Pause autonomous replies',
        'description': 'Scheduled reply-to-messages checks continue but do not reply.'},
    'attention_waiting': {'type': 'boolean', 'title': 'Surface contacts waiting for you'},
    'attention_overdue': {'type': 'boolean', 'title': 'Surface contacts that have not replied'},
    'unanswered_days': {'type': 'integer', 'title': 'Days before surfacing contacts that have not replied',
                        'minimum': 1, 'maximum': 365},
    'attention_high_priority': {'type': 'boolean', 'title': 'Surface high-priority messages'},
    'attention_peer_membership_announcements': {'type': 'boolean',
        'title': 'Surface peers announcing added recipients',
        'description': 'Notify about unverified peer membership announcements. Never grants sharing consent.'},
    'attention_new_unmatched_contact': {'type': 'boolean', 'title': 'Surface new unmatched contacts'},
    'attention_new_matched_contact': {'type': 'boolean', 'title': 'Surface new matched contacts'},
    'notifications': {'type': 'string', 'title': 'Push notifications and email', 'enum': ['attention', 'all_messages', 'none'],
        'description': 'Guides check summaries, not ChatGPT completion alerts or OS permissions.'},
}
FIELDS = {**SCHEMA, 'checking_preferences': {'type': 'string', 'maxLength': 2000}}
NOTIFICATION_FIELDS = [k for k in SCHEMA if k.startswith('attention_') or k in ('unanswered_days', 'notifications')]


def native_values(values):
    return {**values, 'notifications': NOTIFICATION_LABELS[values['notifications']]}


def stored_values(values):
    result = dict(values)
    if 'notifications' in result and isinstance(result['notifications'], str):
        result['notifications'] = {v: k for k, v in NOTIFICATION_LABELS.items()}.get(result['notifications'], result['notifications'])
    return result


UUID = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
SCOPE = re.compile(rf'Event/{UUID}\|{UUID}')


def validate(values):
    if not isinstance(values, dict) or values.keys() - FIELDS.keys():
        raise ValueError('Unknown contact preference.')
    for key, value in values.items():
        schema = FIELDS[key]
        if type(value) is not {'boolean': bool, 'integer': int, 'string': str}[schema['type']]:
            raise ValueError('Invalid preference type: ' + key)
        if 'enum' in schema and value not in schema['enum']:
            raise ValueError('Invalid preference choice: ' + key)
        if 'minimum' in schema and not schema['minimum'] <= value <= schema['maximum']:
            raise ValueError('Invalid preference range: ' + key)
        if 'maxLength' in schema and len(value) > schema['maxLength']:
            raise ValueError('Checking preferences are too long.')
    return values


def find_type(api, own):
    entries = [e for e in api.v1_catalog(fulcra_userid=own)
               if e.get('name') == NAME and e.get('fulcra_userid') == own and e.get('api_version') == 'v1'
               and str(e.get('id')).startswith('Event/') and not e.get('deprecated')]
    # Concurrent first saves may create duplicates; consistently use one.
    return min(entries, key=lambda e: e['id']) if entries else None


def _check_state_shares(api, entry):
    # Do not deliberately use state as a shared channel.
    for share in api.get_datashares():
        if entry and not share.get('share_all_data') and share.get('fulcra_data_types') == [entry['id']]:
            raise ValueError('State storage has a targeted share; use separate storage.')


def _parse(entry):
    if entry is None:
        return dict(version=1, global_preferences={}, overrides={})
    document = json.loads(entry['description'])
    if (not isinstance(document, dict) or document.get('version') != 1
            or not isinstance(document.get('overrides'), dict)):
        raise ValueError('Invalid preferences.')
    validate(document['global_preferences'])
    for scope, overrides in document['overrides'].items():
        if not SCOPE.fullmatch(scope):
            raise ValueError('Invalid preference scope.')
        validate(overrides)
    return document


def _state(api):
    own = api.get_fulcra_userid()
    if not isinstance(own, str) or not own:
        raise ValueError('Missing authenticated account.')
    entry = find_type(api, own)
    _check_state_shares(api, entry)
    return own, entry, _parse(entry)


def load(api):
    return _state(api)[2]


def _save(api, change):
    with LOCK:
        own, entry, document = _state(api)
        change(document)
        description = json.dumps(document, ensure_ascii=False, separators=(',', ':'))
        if entry is None:
            api.create_data_type('Event', {'name': NAME, 'description': description})
        else:
            api.update_data_type('Event', entry['id'].split('/', 1)[1], {'description': description})
        if (current := _state(api))[0] != own or current[2] != document:
            raise ValueError('Preference save not verified; reload before retrying.')
        return document


def scope(data_type, peer_userid):
    return data_type + '|' + peer_userid


def read(api):
    return {**DEFAULTS, **load(api)['global_preferences']}


def update(api, changes):
    validate(changes)
    if not changes:
        raise ValueError('Choose at least one preference.')
    document = _save(api, lambda d: d['global_preferences'].update(changes))
    return {**DEFAULTS, **document['global_preferences']}


def contact(api, key):
    document = load(api)
    overrides = document['overrides'].get(key, {})
    return effective({**DEFAULTS, **document['global_preferences']}, overrides), overrides


def set_overrides(api, key, overrides):
    validate(overrides)
    def change(document):
        if overrides:
            document['overrides'][key] = overrides
        else:
            document['overrides'].pop(key, None)
    _save(api, change)


def effective(global_values, overrides):
    result = {**global_values, **overrides}
    # A global pause applies to every contact.
    result['pause_autonomous_replies'] = global_values['pause_autonomous_replies'] or overrides.get(
        'pause_autonomous_replies', False)
    return result
