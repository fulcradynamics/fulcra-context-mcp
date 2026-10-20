from fulcra_mcp import connection
from test_connection_send import API, OWN, PEER, OUT, MID


class EndAPI(API):
    def __init__(self):
        super().__init__()
        self.deleted = []; self.updates = []; self.deprecated = False
    def v1_catalog_schema(self, *a):
        from fulcra_api.connections import CHANNEL_FIELDS
        return CHANNEL_FIELDS
    def resolve_data_type(self, channel, fulcra_userid):
        return [dict(e, deprecated=self.deprecated) for e in super().resolve_data_type(channel, fulcra_userid)]
    def delete_datashare(self, share_id):
        self.deleted.append(share_id)
        self.shares = [s for s in self.shares if s['id'] != share_id]
    def update_data_type(self, base, uuid, body):
        self.updates.append((base, uuid, body)); self.deprecated = body['deprecated']


def end(api, **kw):
    return connection.end(api, **(dict(data_type=OUT, peer_userid=PEER) | kw))


def test_deletes_own_share_only_and_keeps_channel():
    api = EndAPI()
    assert end(api) == dict(data_type=OUT, peer_userid=PEER, ended=True, archived=False, status='ended')
    assert api.deleted == [MID] and api.updates == []


def test_archive_is_verified():
    api = EndAPI()
    assert end(api, archive=True)['archived'] is True
    assert api.updates == [('Event', OUT.split('/')[1], {'deprecated': True})]


def test_unverified_archive_reports_partial():
    api = EndAPI()
    api.update_data_type = lambda *a: None
    result = end(api, archive=True)
    assert result['status'] == 'partial' and result['ended'] and not result['archived']


def test_refuses_multiparty_or_wrong_peer_without_writes():
    api = EndAPI()
    api.shares[0]['permissions'].append(dict(allowed_fulcra_userid='00000000-0000-4000-8000-0000000000aa'))
    assert end(api)['status'] == 'rejected' and api.deleted == []
    assert end(EndAPI(), peer_userid=OWN)['status'] == 'rejected'


def test_remaining_grant_is_not_ended():
    api = EndAPI()
    api.delete_datashare = lambda share_id: None
    result = end(api, archive=True)
    assert result['status'] == 'rejected' and not result['ended'] and not api.updates
