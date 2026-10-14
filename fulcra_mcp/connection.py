"""Audience-checked Event connection sends using the SDK's canonical schema.

One authenticated request client; no ambient credentials or sharing changes.
"""
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError

import jsonschema
from fulcra_api import connections, records
from .connection_compatibility import SHARE_NAME_PREFIX

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
            or not entry.get('description', '').startswith('connect-agents-with-anyone channel')
            or entry.get('deprecated') or entry.get('deleted_at')
            or entry.get('api_version') != 'v1'):
        raise ValueError('An active Event connection channel with exact owner identity is required.')
    return entry


def _authorize(api, own, peer, outbox, expected_peer_userids=None):
    entry = channel_entry(api, own, outbox)
    if not entry.get('recordable'):
        raise ValueError('Channel is not recordable.')
    shares = api.get_datashares()
    if not isinstance(shares, list):
        raise ValueError('Could not verify outgoing grants.')
    expected = expected_peer_userids if expected_peer_userids is not None else [peer]
    if (not isinstance(expected, list) or not expected or len(expected) > 32
            or any(not _uuid(p) or p == own for p in expected)
            or len(set(expected)) != len(expected) or peer not in expected):
        raise ValueError('Provide the exact distinct expected peer user IDs, excluding yourself.')
    audience = set()
    covering = []
    for share in shares:
        selectors = share.get('fulcra_data_types')
        if not isinstance(selectors, list) or type(share.get('share_all_data')) is not bool:
            raise ValueError('Malformed outgoing grant; reconcile sharing before sending.')
        if not (share['share_all_data'] or any(s in selectors for s in (outbox, 'Event', '*', 'Event/*'))):
            continue
        permissions = share.get('permissions')
        if (share['share_all_data'] or selectors != [outbox]
                or not isinstance(permissions, list) or not permissions
                or any(not isinstance(p, dict) or not _uuid(p.get('allowed_fulcra_userid'))
                       or p['allowed_fulcra_userid'] == own for p in permissions)
                or any(share.get(k) for k in ('group_permissions', 'group_id', 'file_paths', 'files',
                                              'file_history_paths', 'time_start', 'time_end'))
                or not _uuid(share.get('id') or share.get('datashare_id'))):
            raise ValueError('Every covering grant must share only this channel with direct users, without groups, files or time bounds.')
        audience.update(p['allowed_fulcra_userid'] for p in permissions)
        covering.append(share)
    if not covering or not all(s.get('datashare_name', '').startswith(SHARE_NAME_PREFIX) for s in covering):
        raise ValueError('Narrow direct connection grants are required. Nothing was shared.')
    if audience != set(expected):
        raise ValueError('Channel audience changed or differs from expected_peer_userids. Nothing submitted.')
    return entry


def _target(api, peer, target, now):
    found = []
    channels = set()
    for grant in api.get_shared_datasets():
        types = grant.get('fulcra_data_types')
        if (grant.get('sharing_fulcra_userid') == peer and grant.get('grant_type') == 'user'
                and grant.get('datashare_name', '').startswith(SHARE_NAME_PREFIX)
                and isinstance(types, list) and len(types) == 1
                and re.fullmatch('Event/' + UUID_PATTERN, types[0])
                and not any(grant.get(k) for k in ('share_all_data', 'group_id', 'time_start', 'time_end'))):
            channels.add((peer, types[0]))
    for owner, channel in channels:
        entry = channel_entry(api, owner, channel)
        for row in records.get_records(api, entry, now - connections.REPLY_LOOKBACK, now):
            if row.get('id') == target:
                stamp = datetime.fromisoformat(row['start_time'].replace('Z', '+00:00'))
                if row.get('kind') not in ('message', 'reply') or not now - connections.REPLY_LOOKBACK <= stamp <= now:
                    raise ValueError('Reply/ack target must be a peer message or reply within 30 days, never an ack.')
                found.append(row)
    if len(found) != 1:
        raise ValueError('Missing or ambiguous peer reply target within 30 days.')
    return found[0]


def _readback(api, entry, record):
    now = datetime.now(timezone.utc)
    rows = records.get_records(api, entry, now - timedelta(days=30), now + timedelta(seconds=1))
    matches = [row for row in rows if row.get('id') == record['id']]
    fields = set(connections.CHANNEL_FIELDS['properties']) | {'id'}
    expected = {k: v for k, v in record.items() if k in fields}
    if any({k: v for k, v in row.items() if k in fields} != expected for row in matches):
        raise ValueError('Record ID already has different content; do not overwrite it.')
    return matches[0] if matches else None


def send(api, *, peer_userid, outbox, sender, body, mid, recipients=None,
         kind='message', in_reply_to=None, pri='P2', slug=None, artifacts=None,
         expected_peer_userids=None):
    result = dict(mid=mid, outbox=outbox, peer_userid=peer_userid, peer_acknowledged=False)
    attempted = False
    try:
        if (not _uuid(peer_userid) or not _uuid(mid)
                or not re.fullmatch('Event/' + UUID_PATTERN, outbox)
                or (in_reply_to is not None and not _uuid(in_reply_to))):
            raise ValueError('Use exact UUIDs and an exact Event/<uuid> channel; no normalization is performed.')
        if recipients == []:
            raise ValueError('Omit recipients for everyone; an explicit list cannot be empty.')
        record = connections.build_message(sender=sender, body=body, record_id=mid, kind=kind,
                                           in_reply_to=in_reply_to, recipients=recipients, priority=pri, topic=slug)
        own = api.get_fulcra_userid()
        if not _uuid(own) or own == peer_userid:
            raise ValueError('Could not establish distinct authenticated sender and peer.')
        entry = _authorize(api, own, peer_userid, outbox, expected_peer_userids)
        if in_reply_to:
            target = _target(api, peer_userid, in_reply_to, datetime.now(timezone.utc))
            if slug is None and 'topic' in target:
                record['topic'] = target['topic']
        elif slug is None:
            record['topic'] = 'chat'
        if artifacts is not None:
            record['artifacts'] = artifacts
        jsonschema.validate({k: v for k, v in record.items() if k != 'id'},
                            {'type': 'object', **connections.CHANNEL_FIELDS, 'additionalProperties': False},
                            format_checker=jsonschema.FormatChecker())
        existing = _readback(api, entry, record)
        if existing:
            return {**result, 'status': 'posted', 'record': existing}
        if api.validate_records(outbox, [record], 'v1'):
            raise ValueError('Channel schema validation failed; nothing submitted.')
        for attempt in range(2):
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
                    return {**result, 'status': 'posted', 'record': observed}
                if poll == 0:
                    time.sleep(RETRY_DELAY)
            if uploaded:
                # Acknowledged upload may precede query visibility. Poll, don't repost.
                return {**result, 'status': 'uncertain', 'retryable': False,
                        'reason': 'Upload accepted; exact record not yet visible. Poll for this ID; do not submit it again.'}
        return {**result, 'status': 'uncertain', 'reason': 'Exact record not observed. Retry only with the same ID and content; never bypass host denial.'}
    except Exception as exc:
        if attempted:
            if (isinstance(exc, (ValueError, jsonschema.ValidationError))
                    or isinstance(exc, HTTPError) and exc.code < 500):
                return {**result, 'status': 'uncertain', 'retryable': False,
                        'reason': 'Write not verified; authorization or validation stopped further attempts. Do not retry or bypass denial.'}
            return {**result, 'status': 'uncertain', 'reason': 'Write not verified. Keep this ID and content; do not bypass permission denial.'}
        return {**result, 'status': 'rejected', 'reason': str(exc) if isinstance(exc, (ValueError, jsonschema.ValidationError)) else 'Preflight verification failed. Nothing submitted.'}
