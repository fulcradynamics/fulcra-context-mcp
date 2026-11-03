"""Audience-checked Event connection sends using the SDK's canonical schema.

One authenticated request client; no ambient credentials or sharing changes.
"""
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError

import jsonschema
from fulcra_api import connections, records


UUID_PATTERN = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
RETRY_DELAY = 1


def _uuid(value):
    return isinstance(value, str) and re.fullmatch(UUID_PATTERN, value) is not None


def channel_entry(api, owner, channel):
    entries = api.resolve_data_type(channel, fulcra_userid=owner)
    if len(entries) != 1:
        raise ValueError('Missing or ambiguous channel.')
    entry = entries[0]
    if (entry.get('id') != channel or entry.get('fulcra_userid') != owner
            or entry.get('deprecated') or entry.get('deleted_at')
            or entry.get('api_version') != 'v1'):
        raise ValueError('An active Event connection channel with exact owner identity is required.')
    return entry


def _authorize(api, own, peer, outbox, expected_peer_userids=None):
    from .channel_metadata import is_template
    entry = channel_entry(api, own, outbox)
    if is_template(entry.get('description')) or entry.get('name') == 'connect-our-agents-standing-invitation':
        raise ValueError('An open invitation template is not a contact channel.')
    if not entry.get('recordable'):
        raise ValueError('Channel is not recordable.')
    shares = api.get_datashares()
    expected = expected_peer_userids if expected_peer_userids is not None else [peer]
    if (not isinstance(expected, list) or not expected or len(expected) > 32
            or any(not _uuid(p) or p == own for p in expected)
            or len(set(expected)) != len(expected) or peer not in expected):
        raise ValueError('Provide the exact distinct expected peer user IDs, excluding yourself.')
    narrow_audience = set()
    for share in shares:
        selectors = share.get('fulcra_data_types') or []
        if share.get('share_all_data') or selectors != [outbox]:
            continue
        permissions = share.get('permissions')
        if (any(s.startswith(('file:', 'filehistory:')) for s in selectors)
                or not isinstance(permissions, list) or not permissions
                or any(not isinstance(p, dict) or not _uuid(p.get('allowed_fulcra_userid'))
                       or p['allowed_fulcra_userid'] == own for p in permissions)
                or any(share.get(k) for k in ('group_permissions', 'group_id', 'file_paths', 'files',
                                              'file_history_paths', 'time_start', 'time_end'))
                or not _uuid(share.get('id') or share.get('datashare_id'))):
            raise ValueError('Narrow channel grants must have direct users, without groups, files or time bounds.')
        recipients = {p['allowed_fulcra_userid'] for p in permissions}
        narrow_audience.update(recipients)
    # Broad overlaps may not establish or expand a connection's audience.
    if narrow_audience != set(expected):
        raise ValueError('Narrow direct connection grants are required. Nothing was shared.')
    return entry


def owned_connection(api, data_type, peer_userid, expected_peer_userids=None):
    """Authorize an owned Event connection before reading or editing metadata."""
    from .tools import _user_defined_fields
    from .mentions import _compatible_schema

    if not re.fullmatch('Event/' + UUID_PATTERN, data_type) or not _uuid(peer_userid):
        raise ValueError('Exact Event channel and peer UUID required.')
    own = api.get_fulcra_userid()
    if not _uuid(own) or own == peer_userid:
        raise ValueError('Distinct authenticated owner required.')
    entry = _authorize(api, own, peer_userid, data_type, expected_peer_userids)
    fields, required = _user_defined_fields(api.v1_catalog_schema(data_type, 'v1'))
    if (entry.get('record_spec', {}).get('type') != 'event'
            or not _compatible_schema({'fields': fields, 'required_fields': required})):
        raise ValueError('Event connection schema required.')
    return own, entry


def _readback(api, entry, record):
    now = datetime.now(timezone.utc)
    rows = records.get_records(api, entry, now - timedelta(days=30), now + timedelta(seconds=1))
    return next((row for row in rows if row.get('id') == record['id']), None)


def _clear_status(api, entry):
    """Remove the previous assessment after a confirmed send, best effort."""
    from .contact_status import parse_status, remove_status
    try:
        entry = channel_entry(api, entry['fulcra_userid'], entry['id'])
        if parse_status(entry.get('description')) is None:
            return False
        description = remove_status(entry['description'])
        api.update_data_type('Event', entry['id'].split('/')[1], {'description': description})
        return channel_entry(api, entry['fulcra_userid'], entry['id']).get('description') == description
    except Exception:
        return False


def send(api, *, peer_userid, outbox, sender, body, mid, recipients=None,
         kind='message', in_reply_to=None, pri='P2', slug=None, artifacts=None,
         expected_peer_userids=None, max_attempts=2):
    result = dict(mid=mid, outbox=outbox, peer_userid=peer_userid, peer_acknowledged=False)

    def posted(entry, row):
        # A message or reply answers the contact; an ack only marks read.
        cleared = {} if kind == 'ack' else {'status_cleared': _clear_status(api, entry)}
        return {**result, 'status': 'posted', 'record': row, **cleared}

    attempted = False
    try:
        if (not _uuid(peer_userid) or not _uuid(mid)
                or not re.fullmatch('Event/' + UUID_PATTERN, outbox)):
            raise ValueError('Use exact UUIDs and an exact Event/<uuid> channel; no normalization is performed.')
        if recipients == []:
            raise ValueError('Omit recipients for everyone; an explicit list cannot be empty.')
        record = connections.build_message(sender=sender, body=body, record_id=mid, kind=kind,
                                           in_reply_to=in_reply_to, recipients=recipients, priority=pri, topic=slug)
        if in_reply_to is not None:
            # The SDK canonicalizes UUIDs; references retain their exact spelling.
            record['in_reply_to'] = in_reply_to
        own = api.get_fulcra_userid()
        if not _uuid(own) or own == peer_userid:
            raise ValueError('Could not establish distinct authenticated sender and peer.')
        entry = _authorize(api, own, peer_userid, outbox, expected_peer_userids)
        if slug is None:
            record['topic'] = 'chat'
        if artifacts is not None:
            record['artifacts'] = artifacts
        jsonschema.validate({k: v for k, v in record.items() if k != 'id'},
                            {'type': 'object', **connections.CHANNEL_FIELDS, 'additionalProperties': False},
                            format_checker=jsonschema.FormatChecker())
        existing = _readback(api, entry, record)
        if existing:
            return posted(entry, existing)
        if api.validate_records(outbox, [record], 'v1'):
            raise ValueError('Channel schema validation failed; nothing submitted.')
        for attempt in range(max_attempts):
            # Revalidate even on retry; grants and record ingestion are not atomic.
            _authorize(api, own, peer_userid, outbox, expected_peer_userids)
            if api.get_fulcra_userid() != own:
                raise ValueError('Authenticated account changed.')
            attempted = True
            uploaded = False
            try:
                api.record_data_type(outbox, [record], 'v1')
                uploaded = True
            except HTTPError as exc:
                if exc.code < 500:
                    return {**result, 'status': 'uncertain' if attempt else 'rejected',
                            'retryable': False,
                            'reason': 'Permission or validation denied. Do not retry or bypass denial.'}
            except (TimeoutError, ConnectionError, OSError):
                pass  # Uncertain transport: read first, then retry the same payload/ID.
            for poll in range(2):
                observed = _readback(api, entry, record)
                if observed:
                    return posted(entry, observed)
                if poll == 0:
                    time.sleep(RETRY_DELAY)
            if uploaded:
                # Acknowledged upload may precede query visibility. Poll, don't repost.
                return {**result, 'status': 'uncertain', 'retryable': False,
                        'reason': 'Upload accepted; exact record not yet visible. Poll for this ID; do not submit it again.'}
        if max_attempts == 1:
            return {**result, 'status': 'uncertain', 'retryable': False,
                    'reason': 'Exact record not observed. Inspect this ID read-only; do not resend automatically.'}
        return {**result, 'status': 'uncertain', 'reason': 'Exact record not observed. Retry only with the same ID and content; never bypass host denial.'}
    except Exception as exc:
        if attempted:
            if (isinstance(exc, (ValueError, jsonschema.ValidationError))
                    or isinstance(exc, HTTPError) and exc.code < 500):
                return {**result, 'status': 'uncertain', 'retryable': False,
                        'reason': 'Write not verified; authorization or validation stopped further attempts. Do not retry or bypass denial.'}
            return {**result, 'status': 'uncertain', 'reason': 'Write not verified. Keep this ID and content; do not bypass permission denial.'}
        return {**result, 'status': 'rejected', 'reason': str(exc) if isinstance(exc, (ValueError, jsonschema.ValidationError)) else 'Preflight verification failed. Nothing submitted.'}


def end(api, *, data_type, peer_userid, archive=False):
    """End one exact single-peer contact as the connection skill does: delete our
    narrow shares, read back that none remain, then optionally archive our channel.
    Their share with us is left alone."""
    result = dict(data_type=data_type, peer_userid=peer_userid, ended=False, archived=False)
    try:
        own, _ = owned_connection(api, data_type, peer_userid)
        narrow = [s for s in api.get_datashares() if not s.get('share_all_data')
                  and s.get('fulcra_data_types') == [data_type]]
        for share in narrow:
            if api.get_fulcra_userid() != own:
                raise ValueError('Authenticated account changed.')
            api.delete_datashare(share.get('id') or share['datashare_id'])
        remaining = api.get_datashares()
        if any(not s.get('share_all_data') and s.get('fulcra_data_types') == [data_type]
               for s in remaining):
            raise ValueError('A narrow contact grant remains.')
        if any(s.get('share_all_data') or set(s.get('fulcra_data_types') or [])
               & {data_type, 'Event', 'Event/*', '*'} for s in remaining):
            result['broader_access_remains'] = True
        result['ended'] = True
        if archive:
            api.update_data_type('Event', data_type.split('/')[1], {'deprecated': True})
            entries = api.resolve_data_type(data_type, fulcra_userid=own)
            if len(entries) != 1 or not entries[0].get('deprecated'):
                raise ValueError('Archive not verified.')
            result['archived'] = True
        return {**result, 'status': 'ended'}
    except Exception as exc:
        reason = str(exc) if isinstance(exc, ValueError) else 'Not verified. Reload before retrying.'
        return {**result, 'status': 'partial' if result['ended'] else 'rejected', 'reason': reason}
