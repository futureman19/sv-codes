import pytest
from telegram_bot import service, bootstrap


@pytest.mark.parametrize('username,webhook,allowed', [('svcodesbot','',True),('anotherbot','',False),('svcodesbot','https://example.org/hook',False)])
def test_identity_before_poll(monkeypatch, tmp_path, username, webhook, allowed):
    events=[]
    class FakeTelegram:
        def __init__(self, token): self.client=self
        def close(self): events.append('closed')
        def request(self, method, data):
            events.append(method)
            if method=='getMe': return {'is_bot':True,'username':username}
            if method=='getWebhookInfo': return {'url':webhook}
            raise AssertionError('Unexpected API operation')
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','123:synthetic-test-only')
    monkeypatch.setenv('TELEGRAM_EXPECTED_USERNAME','svcodesbot')
    monkeypatch.setenv('TELEGRAM_STATE_DB',str(tmp_path/'state.db'))
    monkeypatch.setattr(service,'Telegram',FakeTelegram)
    def stop(_self):
        events.append('poll')
        raise KeyboardInterrupt
    monkeypatch.setattr(service.Bot,'poll',stop)
    with pytest.raises(KeyboardInterrupt if allowed else SystemExit): service.run()
    assert ('poll' in events)==allowed
    assert events[0]=='getMe'


def test_drop_privileges_before_service(monkeypatch):
    events=[]
    class FakePath:
        def __init__(self,p): assert p=='/data'
        def mkdir(self,exist_ok): events.append('mkdir')
    monkeypatch.setattr(bootstrap,'Path',FakePath)
    monkeypatch.setattr(bootstrap.os,'geteuid',lambda:0,raising=False)
    for method in ['chown','setgroups','setgid','setuid']:
        monkeypatch.setattr(bootstrap.os,method,lambda *args,m=method:events.append((m,args)),raising=False)
    monkeypatch.setattr(service,'run',lambda:events.append('run'))
    monkeypatch.setenv('HOME','test')
    bootstrap.main()
    assert events==['mkdir',('chown',('/data',10001,10001)),('setgroups',([],)),('setgid',(10001,)),('setuid',(10001,)),'run']
