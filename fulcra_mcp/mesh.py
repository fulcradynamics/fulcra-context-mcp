"""Native mesh v1 sending, adapted from the Hermes mesh operations.

No connection state, sharing, LLM, or ambient credentials: the caller supplies
one authenticated request client. Account identity is never a tool argument.
"""
import json
import re
from datetime import datetime, timedelta, timezone

from fulcra_api import records

UUID_PATTERN = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'


def _uuid(value):
    return isinstance(value, str) and re.fullmatch(UUID_PATTERN, value) is not None


def _envelope(row):
    try:
        value = json.loads(row.get('note', ''))
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _authorize(api, own, peer, outbox):
    entries = api.resolve_data_type(outbox, fulcra_userid=own)
    if len(entries) != 1:
        raise ValueError('Missing or ambiguous own outbox.')
    entry = entries[0]
    if (entry.get('id') != outbox or entry.get('fulcra_userid') != own
            or not re.search(r'\bmesh outbox\b', entry.get('name', ''), re.I)
            or entry.get('deprecated') or entry.get('deleted_at') or not entry.get('recordable')
            or entry.get('api_version') != 'v1alpha1'):
        raise ValueError('An active, owned MomentAnnotation Mesh Outbox is required.')
    shares = api.get_datashares()
    if not isinstance(shares, list):
        raise ValueError('Could not verify outgoing grants.')
    covering = []
    for share in shares:
        selectors = share.get('fulcra_data_types')
        if not isinstance(selectors, list) or type(share.get('share_all_data')) is not bool:
            raise ValueError('Malformed outgoing grant; reconcile sharing before sending.')
        if not (share['share_all_data'] or any(s in selectors for s in (outbox, 'MomentAnnotation', '*', 'MomentAnnotation/*'))):
            continue
        permissions = share.get('permissions')
        if (share['share_all_data'] or selectors != [outbox]
                or not isinstance(permissions, list) or len(permissions) != 1
                or permissions[0].get('allowed_fulcra_userid') != peer
                or any(share.get(k) for k in ('group_permissions', 'group_id', 'file_paths', 'files',
                                              'file_history_paths', 'time_start', 'time_end'))
                or not _uuid(share.get('id') or share.get('datashare_id'))):
            raise ValueError('Every covering grant must share only this outbox with exactly this peer, without groups, files or time bounds.')
        covering.append(share)
    if len(covering) != 1:
        raise ValueError('Exactly one narrow direct outbox grant is required. Reconcile shares manually; nothing was shared.')
    return entry


def send(api, *, peer_userid, outbox, peer_agent, body, mid, kind, pri, slug):
    result = dict(mid=mid, outbox=outbox, peer_userid=peer_userid, peer_acknowledged=False)
    attempted = False
    try:
        if (not _uuid(peer_userid) or not _uuid(mid)
                or not re.fullmatch('MomentAnnotation/' + UUID_PATTERN, outbox)):
            raise ValueError('Use exact UUIDs and an exact MomentAnnotation/<uuid> outbox; no normalization is performed.')
        if not body.strip() or len(body) > 24000:
            raise ValueError('Message must be nonblank and at most 24000 characters.')
        if not peer_agent.strip() or len(peer_agent) > 200 or not slug.strip() or len(slug) > 200:
            raise ValueError('Exact recipient agent and slug must be nonblank and at most 200 characters.')
        own = api.get_fulcra_userid()
        if not _uuid(own) or own == peer_userid:
            raise ValueError('Could not establish a distinct authenticated sender and peer.')
        entry = _authorize(api, own, peer_userid, outbox)
        envelope = dict(v=1, mid=mid, to=peer_agent, to_user=peer_userid, kind=kind, pri=pri, slug=slug, body=body)
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        rows = records.get_records(api, entry, start, now)
        matches = [_envelope(row) for row in rows if _envelope(row).get('mid') == mid]
        if matches:
            if any(env != envelope for env in matches):
                raise ValueError('Message ID already has different content. Reconcile the outbox; do not resend.')
            return {**result, 'status': 'posted', 'record': next(row for row in rows if _envelope(row) == envelope)}
        record = {'sources': ['com.fulcradynamics.mcp', 'com.fulcradynamics.annotation.' + outbox.split('/')[1]],
                  'recorded_at': now.isoformat(), 'note': json.dumps(envelope, ensure_ascii=False)}
        if api.validate_records('MomentAnnotation', [record], 'v1alpha1'):
            raise ValueError('The outbox record failed schema validation; nothing posted.')
        # Recheck immediately before writing. The service has no transaction
        # spanning grants and records; callers must not promise atomic revocation.
        _authorize(api, own, peer_userid, outbox)
        if api.get_fulcra_userid() != own:
            raise ValueError('Authenticated account changed; nothing posted.')
        attempted = True
        api.record_data_type('MomentAnnotation', [record], 'v1alpha1')
        rows = records.get_records(api, entry, start, datetime.now(timezone.utc) + timedelta(seconds=1))
        matching = [row for row in rows if _envelope(row) == envelope]
        if matching:
            return {**result, 'status': 'posted', 'record': matching[0]}
        return {**result, 'status': 'uncertain', 'reason': 'Upload returned, but exact envelope not observed in readback. Reconcile this mid; do not resend.'}
    except Exception as exc:
        if attempted:
            return {**result, 'status': 'uncertain', 'reason': 'Could not verify the attempted write. Reconcile this mid in the outbox before sending again; no automatic resend.'}
        return {**result, 'status': 'rejected', 'reason': str(exc) if isinstance(exc, ValueError) else 'Preflight verification failed. Nothing submitted.'}
