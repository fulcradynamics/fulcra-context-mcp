"""Durable, narrowly authorized invitation return shares.

Peer content is only a lookup token. Identity comes from current direct grants.
Uncertain writes consume the invitation and are never automatically retried.
"""
import json
import logging
import re
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import RLock
from urllib.error import HTTPError

from fulcra_api import connections

from .connection import UUID_PATTERN, _uuid, channel_entry, _authorize
from .connection_compatibility import SHARE_NAME_PREFIX
from .contact_preferences import _check_private

NAME = 'Fulcra Agent Invitations'
STANDING_NAME = 'connect-our-agents-standing-invitation'
STANDING_INVITER = 'standing_invitation_inviter: '
LOCK = RLock()  # Storage has no compare-and-swap; serialize this worker.
CODE = re.compile('[0-9a-f]{32}')
logger = logging.getLogger(__name__)


class _EvidenceUnavailable(Exception):
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__('Invitation evidence unavailable.')


def _diagnostic(exc, stage):
    # Never include exception text, URLs, response bodies, or peer content.
    if isinstance(exc, _EvidenceUnavailable):
        return exc.diagnostic
    if isinstance(exc, HTTPError):
        return dict(stage=stage, category='http', http_status=exc.code)
    if isinstance(exc, OSError):
        category = 'transport'
    elif isinstance(exc, (ValueError, TypeError, KeyError)):
        category = 'validation'
    else:
        category = 'unexpected'
    return dict(stage=stage, category=category)


@contextmanager
def _checking(stage):
    try:
        yield
    except Exception as exc:
        raise _EvidenceUnavailable(_diagnostic(exc, stage)) from None


def _history(api, owner, channel):
    # The SDK's get_records encodes the whole range as seconds. The backend
    # PromQL parser rejects a seconds component larger than uint32. Use days
    # plus seconds, retaining the SAME year-1 lower bound, never a lookback.
    end = datetime.now(timezone.utc).replace(microsecond=0)
    duration = end - datetime(1, 1, 1, tzinfo=timezone.utc)
    span = f'{duration.days}d' + (f'{duration.seconds}s' if duration.seconds else '')
    query = f'{{__name__="{channel}"}}[{span}] @ {int(end.timestamp())}'
    response = api.fulcra_v1_records(query, fulcra_userid=owner)
    # Consume every JSONL line; a partial/malformed response must fail closed.
    return [json.loads(line) for line in response.splitlines() if line.strip()]


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
    outboxes = set(document['invitations'])
    for channel, invite in document['invitations'].items():
        if (not re.fullmatch('Event/' + UUID_PATTERN, channel) or not isinstance(invite, dict)
                or not isinstance(invite.get('code'), str) or not CODE.fullmatch(invite['code'])
                or invite.get('state') not in ('prepared', 'consumed', 'completed')):
            raise ValueError('Invalid invitation.')
        if invite['state'] != 'prepared' and (not _uuid(invite.get('peer_userid'))
                or not re.fullmatch('Event/' + UUID_PATTERN, invite.get('incoming_data_type', ''))):
            raise ValueError('Invalid invitation binding.')
        prefix = invite.get('prefix', 'handshake')
        if prefix not in ('handshake', 'open_invitation'):
            raise ValueError('Invalid invitation prefix.')
        if prefix == 'open_invitation':
            if invite['state'] != 'prepared' or not isinstance(invite.get('responses'), dict):
                raise ValueError('Invalid open invitation.')
            for peer, binding in invite['responses'].items():
                if (not _uuid(peer) or not isinstance(binding, dict)
                        or binding.get('state') not in ('creating', 'prepared', 'consumed', 'completed')
                        or not re.fullmatch('Event/' + UUID_PATTERN, binding.get('incoming_data_type', ''))):
                    raise ValueError('Invalid open invitation binding.')
                if binding['state'] != 'creating':
                    outbox = binding.get('data_type', '')
                    if not re.fullmatch('Event/' + UUID_PATTERN, outbox) or outbox in outboxes:
                        raise ValueError('Invalid individual outbox.')
                    outboxes.add(outbox)
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
    return [share for share in api.get_datashares()
            if share.get('share_all_data') or set(share.get('fulcra_data_types') or []) & {channel, 'Event', 'Event/*', '*'}]


def prepare(api, data_type, open_invitation=False):
    with LOCK:
        own, entry, document = _state(api)
        if any(binding.get('data_type') == data_type
               for invitation in document['invitations'].values()
               for binding in invitation.get('responses', {}).values()):
            raise ValueError('Individual outbox already bound to an open invitation.')
        _channel(api, own, data_type, own=True)
        if _covering(api, data_type):
            raise ValueError('Prepare an unshared channel; no audience changes are authorized.')
        invite = document['invitations'].get(data_type)
        prefix = 'open_invitation' if open_invitation else 'handshake'
        if invite and invite.get('prefix', 'handshake') != prefix:
            raise ValueError('Invitation mode cannot change.')
        if invite and invite['state'] != 'prepared':
            raise ValueError('Invitation already consumed. Do not reuse it.')
        if not invite:
            code = secrets.token_hex(16)
            if code in {i['code'] for i in document['invitations'].values()}:
                raise ValueError('Code collision; prepare again.')
            invite: dict = {'code': code, 'state': 'prepared', 'prefix': prefix}
            if open_invitation:
                invite['responses'] = {}
            document['invitations'][data_type] = invite
            _save(api, own, entry, document)
        return dict(status='prepared', data_type=data_type, own_userid=own,
                    code=invite['code'], topic=prefix + ' ' + invite['code'])


def _evidence(api, own, prefix='handshake'):
    with _checking('incoming_grants'):
        grants = api.get_shared_datasets()
    channels = set()
    for grant in grants:
        if grant.get('grant_type') in ('self', 'group'):
            continue
        types = grant.get('fulcra_data_types') or []
        if (grant.get('grant_type') == 'user' and _uuid(grant.get('sharing_fulcra_userid'))
                and grant['sharing_fulcra_userid'] != own
                and isinstance(grant.get('datashare_name'), str)
                and grant['datashare_name'].startswith(SHARE_NAME_PREFIX)
                and len(types) == 1 and re.fullmatch('Event/' + UUID_PATTERN, types[0])
                and not any(grant.get(k) for k in ('share_all_data', 'group_id', 'time_start', 'time_end'))):
            channels.add((grant['sharing_fulcra_userid'], types[0]))
    evidence = {}
    for owner, channel in sorted(channels):
        with _checking('incoming_channel'):
            _channel(api, owner, channel)
        with _checking('handshake_history'):
            rows = _history(api, owner, channel)
            if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                raise ValueError('Incomplete handshake history.')
        with _checking('handshake_timestamps'):
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
        marker = prefix + ' '
        if isinstance(topic, str) and topic.startswith(marker) and CODE.fullmatch(topic[len(marker):]):
            evidence.setdefault(topic[len(marker):], []).append((owner, channel, first[0].get('sender')))
    if prefix == 'open_invitation':
        return evidence
    return {code: peers[0][:2] for code, peers in evidence.items() if len(peers) == 1}


def _open_peer(api, own, code, peer):
    rows = [r for r in _evidence(api, own, 'open_invitation').get(code, []) if r[0] == peer]
    return rows[0][:2] if len(rows) == 1 else None


def _match_open(api, own, document, template, invite):
    from fulcra_api import data_type_management
    from .contact_identifier import parse_contact_identifier, write_contact_identifier, validate_identifier

    results = []
    rows = _evidence(api, own, 'open_invitation').get(invite['code'], [])
    for peer, incoming, sender in rows:
        binding = invite['responses'].get(peer)
        if binding and binding['state'] == 'completed':
            continue
        result: dict = dict(template_data_type=template, peer_userid=peer,
                      incoming_data_type=incoming, status='pending')
        results.append(result)
        try:
            pair = (peer, incoming)
            def verify():
                current_own, entry, current = _state(api)
                if (current_own != own or current != document
                        or _open_peer(api, own, invite['code'], peer) != pair
                        or _covering(api, template)):
                    raise ValueError('Open invitation evidence changed.')
                return entry

            entry = verify()
            source = _channel(api, own, template, own=True)
            if binding and binding['incoming_data_type'] != incoming:
                raise ValueError('Responder already bound to another source.')
            if not binding:
                # Persist intent BEFORE creation: an uncertain create must not duplicate.
                label = parse_contact_identifier(source.get('description')) or template
                try:
                    sender = validate_identifier(sender[:80].strip())
                except (ValueError, TypeError):
                    sender = 'Agent'
                identifier = sender[:max(1, 75 - len(label))] + ' via ' + label[:74]
                identifier = identifier[:80].strip()
                description = write_contact_identifier(_without_inviter(source.get('description') or ''), identifier)
                entry = verify()
                binding = dict(state='creating', incoming_data_type=incoming, identifier=identifier)
                invite['responses'][peer] = binding
                _save(api, own, entry, document)
                # Responders never inherit the standing template's unique name.
                created = data_type_management.create_data_type(api, {'id': 'Event', 'api_version': 'v1'},
                    identifier if source.get('name') == STANDING_NAME else source.get('name') or 'Agent connection',
                    description=description,
                    fields_schema={'properties': connections.CHANNEL_FIELDS['properties'],
                                   'required': connections.CHANNEL_FIELDS['required']})
                data_type = created['id']
                if data_type == template or data_type in document['invitations']:
                    raise ValueError('New individual outbox required.')
                _channel(api, own, data_type, own=True)
                if _covering(api, data_type):
                    raise ValueError('New outbox already shared.')
                entry = verify()
                binding.update(data_type=data_type, state='prepared')
                _save(api, own, entry, document)
            if binding['state'] == 'creating':
                raise ValueError('Prior creation not verified; no automatic retry.')
            data_type = binding['data_type']
            result.update(data_type=data_type, identifier=binding['identifier'])
            _channel(api, own, data_type, own=True)
            covering = _covering(api, data_type)
            if covering:
                _authorize(api, own, peer, data_type)
            elif binding['state'] == 'consumed':
                raise ValueError('Prior share not verified; no automatic retry.')
            if binding['state'] == 'prepared':
                entry = verify()
                binding['state'] = 'consumed'
                _save(api, own, entry, document)
                verify()
                if _covering(api, data_type):
                    _authorize(api, own, peer, data_type)
                else:
                    api.create_datashare(datashare_name='connect-our-agents invitation',
                        fulcra_data_types=[data_type], allowed_user_ids=[peer], share_all_data=False,
                        allowed_group_ids=None, time_start=None, time_end=None)
            _authorize(api, own, peer, data_type)
            entry = verify()
            binding['state'] = 'completed'
            _save(api, own, entry, document)
            result['status'] = 'matched'
        except Exception as exc:
            result['reason'] = 'Match not verified. No automatic write retry.'
            result['diagnostic'] = _diagnostic(exc, 'open_match_verification')
    return results


def match(api):
    results = []
    with LOCK:
        try:
            own, _, document = _state(api)
            if all(i['state'] == 'completed' for i in document['invitations'].values()):
                return {'results': []}
            evidence = _evidence(api, own)
            for data_type, invite in document['invitations'].items():
                if invite.get('prefix') == 'open_invitation':
                    results.extend(_match_open(api, own, document, data_type, invite))
                    continue
                if invite['state'] == 'completed':
                    continue  # Discovery owns the connection's subsequent grant lifecycle.
                result: dict = dict(data_type=data_type, status='pending')
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
                except Exception as exc:
                    result['reason'] = 'Match not verified. No automatic write retry.'
                    result['diagnostic'] = _diagnostic(exc, 'match_verification')
                    logger.warning('Invitation match failed: %s', result['diagnostic'])
        except Exception as exc:
            diagnostic = _diagnostic(exc, 'invitation_evidence')
            logger.warning('Invitation evidence failed: %s', diagnostic)
            return {'results': [], 'status': 'unavailable',
                    'reason': 'Invitation evidence unavailable; nothing shared.',
                    'diagnostic': diagnostic}
    return {'results': results}


def _inviter_marker(description):
    """(start, end, name) of the saved inviter name, wherever whitespace folding
    put it, or None."""
    start = (description or '').find(STANDING_INVITER)
    if start < 0:
        return None
    name, end = json.JSONDecoder().raw_decode(description, start + len(STANDING_INVITER))
    return start, end, name


def _standing_inviter(description):
    marker = _inviter_marker(description)
    return marker[2] if marker else ''


def _without_inviter(description):
    # Responder outboxes copy the template description; the name stays private.
    marker = _inviter_marker(description)
    if not marker:
        return description
    return description[:marker[0]].rstrip(' \t\r\n') + description[marker[1]:]


def _standing_entry(api, own):
    entries = [e for e in api.v1_catalog(fulcra_userid=own)
               if e.get('name') == STANDING_NAME and e.get('fulcra_userid') == own
               and e.get('api_version') == 'v1' and e.get('id', '').startswith('Event/')
               and not e.get('deprecated') and not e.get('deleted_at')]
    if len(entries) > 1:
        raise ValueError('Ambiguous standing invitation.')
    return entries[0] if entries else None


def standing(api, inviter_name=None):
    """Return the user's standing open invitation, creating it on first use.
    A given inviter_name ('' clears it) is saved on the private template."""
    from fulcra_api import data_type_management
    from .contact_identifier import write_contact_identifier, validate_identifier

    if inviter_name:
        inviter_name = validate_identifier(inviter_name.strip())
    with LOCK:
        own = api.get_fulcra_userid()
        entry = _standing_entry(api, own)
        if not entry:
            data_type_management.create_data_type(
                api, {'id': 'Event', 'api_version': 'v1'}, STANDING_NAME,
                description=write_contact_identifier(f'{SHARE_NAME_PREFIX[-1]} channel', 'Open invitation'),
                fields_schema={'properties': connections.CHANNEL_FIELDS['properties'],
                               'required': connections.CHANNEL_FIELDS['required']})
            entry = _standing_entry(api, own)
            if not entry:
                raise ValueError('Standing invitation not verified.')
        prepared = prepare(api, entry['id'], open_invitation=True)
        if inviter_name is not None and inviter_name != _standing_inviter(entry['description']):
            description = _without_inviter(entry['description'])
            if inviter_name:
                # Before the final label suffix, which must stay last.
                from .contact_identifier import _marker
                label = _marker(description)
                index = label[0] if label else len(description)
                description = (description[:index].rstrip(' \t\r\n') + '\n' + STANDING_INVITER
                               + json.dumps(inviter_name) + ('\n' + description[index:] if label else ''))
            api.update_data_type('Event', entry['id'].split('/')[1], {'description': description})
            entry = _standing_entry(api, own)
            if not entry or _standing_inviter(entry['description']) != inviter_name:
                raise ValueError('Name not saved.')
        return {**prepared, 'inviter_name': _standing_inviter(entry['description'])}


def create(api, inviter_name, recipient_name, recipient_userid=None):
    """Create a labeled single-person invitation outbox, as the invite skill does,
    then prepare its code. A known recipient ID shares the outbox up front; their
    handshake still completes the match."""
    from fulcra_api import data_type_management
    from .contact_identifier import write_contact_identifier, validate_identifier

    inviter, recipient = validate_identifier(inviter_name.strip()), validate_identifier(recipient_name.strip())
    identifier = validate_identifier(f"{recipient}'s agent")
    with LOCK:
        own = api.get_fulcra_userid()
        if recipient_userid is not None and (not _uuid(recipient_userid) or recipient_userid == own):
            raise ValueError("Use the other person's exact Fulcra user ID, or leave it blank.")
        created = data_type_management.create_data_type(
            api, {'id': 'Event', 'api_version': 'v1'}, f'{inviter} with {recipient}',
            description=write_contact_identifier(f'{SHARE_NAME_PREFIX[-1]} channel', identifier),
            fields_schema={'properties': connections.CHANNEL_FIELDS['properties'],
                           'required': connections.CHANNEL_FIELDS['required']})
        data_type = created['id']
        _channel(api, own, data_type, own=True)
        prepared = prepare(api, data_type)
        if recipient_userid:
            api.create_datashare(datashare_name=f'{SHARE_NAME_PREFIX[-1]}: {identifier}',
                fulcra_data_types=[data_type], allowed_user_ids=[recipient_userid], share_all_data=False,
                allowed_group_ids=None, time_start=None, time_end=None)
            _authorize(api, own, recipient_userid, data_type)
        return {**prepared, 'identifier': identifier, 'shared_with': recipient_userid}
