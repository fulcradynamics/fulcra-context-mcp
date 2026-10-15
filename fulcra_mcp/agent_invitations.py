"""Durable, narrowly authorized invitation return shares.

Peer content is only a lookup token. Identity comes from current direct grants.
Uncertain writes consume the invitation and are never automatically retried.
"""
import json
import re
import secrets
from datetime import datetime, timezone
from threading import RLock

from fulcra_api import records
from .connection import UUID_PATTERN, _uuid, channel_entry, _authorize
from .connection_compatibility import SHARE_NAME_PREFIX
from .contact_preferences import _check_private

NAME = 'Fulcra Agent Invitations'
LOCK = RLock()  # Storage has no compare-and-swap; serialize this worker.
CODE = re.compile('[0-9a-f]{32}')


def _channel(api, owner, data_type, own=False):
    from .tools import _user_defined_fields
    from .mentions import _compatible_schema
    if not isinstance(data_type, str) or not re.fullmatch('Event/' + UUID_PATTERN, data_type):
        raise ValueError('Exact Event channel required.')
    entry = channel_entry(api, owner, data_type)
    fields, required = _user_defined_fields(api.v1_catalog_schema(data_type, 'v1', fulcra_userid=owner))
    if (entry.get('record_spec', {}).get('type') != 'event'
            or own and not entry.get('recordable')
            or not _compatible_schema({'fields': fields, 'required_fields': required})):
        raise ValueError('Compatible connection schema required.')
    return entry


def _state(api):
    own = api.get_fulcra_userid()
    if not _uuid(own):
        raise ValueError('Authenticated owner required.')
    catalog = api.v1_catalog(fulcra_userid=own)
    if not isinstance(catalog, list):
        raise ValueError('Invitation catalog unavailable.')
    entries = [e for e in catalog if e.get('name') == NAME and e.get('fulcra_userid') == own
               and e.get('api_version') == 'v1' and e.get('id', '').startswith('Event/')
               and not e.get('deprecated') and not e.get('deleted_at')]
    if len(entries) > 1:
        raise ValueError('Ambiguous invitation storage.')
    entry = entries[0] if entries else None
    _check_private(api, entry)
    document = json.loads(entry['description']) if entry else {'version': 1, 'invitations': {}}
    if document.get('version') != 1 or not isinstance(document.get('invitations'), dict):
        raise ValueError('Invalid invitation storage.')
    codes = []
    for channel, invite in document['invitations'].items():
        if (not re.fullmatch('Event/' + UUID_PATTERN, channel) or not isinstance(invite, dict)
                or not isinstance(invite.get('code'), str) or not CODE.fullmatch(invite['code'])
                or invite.get('state') not in ('prepared', 'consumed', 'completed')):
            raise ValueError('Invalid invitation.')
        if invite['state'] != 'prepared' and (not _uuid(invite.get('peer_userid'))
                or not re.fullmatch('Event/' + UUID_PATTERN, invite.get('incoming_data_type', ''))):
            raise ValueError('Invalid invitation binding.')
        codes.append(invite['code'])
    if len(set(codes)) != len(codes):
        raise ValueError('Duplicate invitation codes.')
    return own, entry, document


def _save(api, own, entry, document):
    description = json.dumps(document, separators=(',', ':'))
    if api.get_fulcra_userid() != own:
        raise ValueError('Account changed.')
    _check_private(api, entry)
    if entry:
        api.update_data_type('Event', entry['id'].split('/')[1], {'description': description})
    else:
        api.create_data_type('Event', {'name': NAME, 'description': description})
    current = _state(api)
    if current[0] != own or current[2] != document:
        raise ValueError('Invitation save not verified.')
    return current


def _covering(api, channel):
    shares = api.get_datashares()
    if not isinstance(shares, list):
        raise ValueError('Outgoing grants unavailable.')
    covering = []
    for share in shares:
        if type(share.get('share_all_data')) is not bool or not isinstance(share.get('fulcra_data_types'), list):
            raise ValueError('Incomplete outgoing grants.')
        if share['share_all_data'] or set(share['fulcra_data_types']) & {channel, 'Event', 'Event/*', '*'}:
            covering.append(share)
    return covering


def prepare(api, data_type):
    with LOCK:
        own, entry, document = _state(api)
        _channel(api, own, data_type, own=True)
        if _covering(api, data_type):
            raise ValueError('Prepare an unshared channel; no audience changes are authorized.')
        invite = document['invitations'].get(data_type)
        if invite and invite['state'] != 'prepared':
            raise ValueError('Invitation already consumed. Do not reuse it.')
        if not invite:
            code = secrets.token_hex(16)
            if code in {i['code'] for i in document['invitations'].values()}:
                raise ValueError('Code collision; prepare again.')
            invite = {'code': code, 'state': 'prepared'}
            document['invitations'][data_type] = invite
            _save(api, own, entry, document)
        return dict(status='prepared', data_type=data_type, own_userid=own,
                    code=invite['code'], topic='handshake ' + invite['code'])


def _evidence(api, own):
    grants = api.get_shared_datasets()
    if not isinstance(grants, list):
        raise ValueError('Incoming grants unavailable.')
    channels = set()
    for grant in grants:
        if grant.get('grant_type') in ('self', 'group'):
            continue
        types = grant.get('fulcra_data_types')
        if not isinstance(types, list):
            raise ValueError('Incomplete incoming grants.')
        if (grant.get('grant_type') == 'user' and _uuid(grant.get('sharing_fulcra_userid'))
                and grant['sharing_fulcra_userid'] != own
                and grant.get('datashare_name', '').startswith(SHARE_NAME_PREFIX)
                and len(types) == 1 and re.fullmatch('Event/' + UUID_PATTERN, types[0])
                and not any(grant.get(k) for k in ('share_all_data', 'group_id', 'time_start', 'time_end'))):
            channels.add((grant['sharing_fulcra_userid'], types[0]))
    evidence = {}
    for owner, channel in sorted(channels):
        entry = _channel(api, owner, channel)
        # Full history, not a recent/latest-record window. The SDK consumes the
        # complete JSONL response and raises on malformed/truncated lines.
        rows = records.get_records(api, entry, datetime(1, 1, 1, tzinfo=timezone.utc), datetime.now(timezone.utc))
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError('Incomplete handshake history.')
        timed = []
        for row in rows:
            stamp = datetime.fromisoformat(row['start_time'].replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                raise ValueError('Invalid handshake timestamp.')
            timed.append((stamp, row))
        if not timed:
            continue
        first_time = min(t for t, _ in timed)
        first = [r for t, r in timed if t == first_time]
        if len(first) != 1 or first[0].get('kind') != 'message':
            continue
        topic = first[0].get('topic', '')
        if isinstance(topic, str) and topic.startswith('handshake ') and CODE.fullmatch(topic[10:]):
            evidence.setdefault(topic[10:], []).append((owner, channel))
    return {code: peers[0] for code, peers in evidence.items() if len(peers) == 1}


def match(api):
    results = []
    with LOCK:
        try:
            own, _, document = _state(api)
            if all(i['state'] == 'completed' for i in document['invitations'].values()):
                return {'results': []}
            evidence = _evidence(api, own)
            for data_type, invite in document['invitations'].items():
                if invite['state'] == 'completed':
                    continue  # Discovery owns the connection's subsequent grant lifecycle.
                result = dict(data_type=data_type, status='pending')
                results.append(result)
                pair = evidence.get(invite['code'])
                if not pair:
                    result['reason'] = 'No unique first-message handshake.'
                    continue
                peer, incoming = pair
                if invite['state'] == 'consumed' and pair != (invite['peer_userid'], invite['incoming_data_type']):
                    result['reason'] = 'Invitation already bound to another source.'
                    continue
                result.update(peer_userid=peer, incoming_data_type=incoming)
                try:
                    _channel(api, own, data_type, own=True)
                    covering = _covering(api, data_type)
                    if covering:
                        _authorize(api, own, peer, data_type)
                    if not covering and invite['state'] == 'consumed':
                        result['reason'] = 'Prior attempt not verified; no automatic retry.'
                        continue
                    if invite['state'] == 'prepared':
                        # Reload all evidence immediately before consuming consent.
                        current_own, entry, current = _state(api)
                        if (current_own != own or current != document
                                or _evidence(api, own).get(invite['code']) != pair):
                            raise ValueError('Invitation evidence changed.')
                        invite.update(state='consumed', peer_userid=peer, incoming_data_type=incoming)
                        _save(api, own, entry, document)
                        _channel(api, own, data_type, own=True)
                        if (api.get_fulcra_userid() != own
                                or _evidence(api, own).get(invite['code']) != pair
                                or _state(api)[2] != document):
                            raise ValueError('Sharing evidence changed.')
                        if _covering(api, data_type):
                            _authorize(api, own, peer, data_type)
                        else:
                            api.create_datashare(datashare_name='connect-our-agents invitation',
                                fulcra_data_types=[data_type], allowed_user_ids=[peer], share_all_data=False,
                                allowed_group_ids=None, time_start=None, time_end=None)
                    # Independent grant readback, never trust a create response.
                    _authorize(api, own, peer, data_type)
                    if api.get_fulcra_userid() != own or _evidence(api, own).get(invite['code']) != pair:
                        raise ValueError('Readback evidence changed.')
                    current_own, entry, current = _state(api)
                    if current_own != own or current != document:
                        raise ValueError('Invitation state changed.')
                    invite['state'] = 'completed'
                    _save(api, own, entry, document)
                    result['status'] = 'matched'
                except Exception:
                    result['reason'] = 'Match not verified. No automatic write retry.'
        except Exception:
            return {'results': [], 'status': 'unavailable', 'reason': 'Invitation evidence unavailable; nothing shared.'}
    return {'results': results}
