import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from india_trader.cloud import create_app, EncryptedVault
from india_trader.brokers.transport import BrokerError


class HostedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = dict(TESTING=True, PUBLIC_ORIGIN='https://desk.example',
            APP_ACCESS_KEY='test-access-' * 4, SESSION_SIGNING_KEY='test-session-' * 4,
            CREDENTIAL_ENCRYPTION_KEY='test-encryption-' * 4, APP_DATA_DIR=self.temp.name)
        self.app = create_app(self.settings)
        self.client = self.app.test_client()
        self.csrf = ''

    def tearDown(self): self.temp.cleanup()

    def get(self, path, **kw):
        return self.client.get(path, base_url=self.settings['PUBLIC_ORIGIN'], headers={'X-Requested-With': 'IndiaTrader'}, **kw)

    def post(self, path, body, origin=None, csrf=None):
        return self.client.post(path, json=body, base_url=self.settings['PUBLIC_ORIGIN'], headers={
            'Origin': origin or self.settings['PUBLIC_ORIGIN'], 'X-CSRF-Token': self.csrf if csrf is None else csrf})

    def login(self):
        response = self.post('/api/login', {'access_key': self.settings['APP_ACCESS_KEY']})
        self.assertEqual(response.status_code, 200)
        self.csrf = response.json['csrf']
        return response

    def test_configuration_fails_closed(self):
        for changes in [dict(APP_ACCESS_KEY='short'), dict(SESSION_SIGNING_KEY=''), dict(CREDENTIAL_ENCRYPTION_KEY=''), dict(APP_DATA_DIR='relative'), dict(PUBLIC_ORIGIN='https://desk.example/path'), dict(TESTING=False), dict(TESTING=False, PUBLIC_ORIGIN='http://desk.example')]:
            with self.subTest(changes=changes), self.assertRaises(ValueError): create_app({**self.settings, **changes})

    def test_private_endpoints_require_login(self):
        for path in ['/api/bootstrap', '/api/docs?name=hosting']:
            self.assertEqual(self.get(path).status_code, 401)
        for path in ['/api/upload', '/api/action', '/api/auth/token']:
            self.assertEqual(self.post(path, {}).status_code, 401)
        self.assertTrue(self.get('/api/session').json['authentication_required'])
        with self.get('/') as response: self.assertEqual(response.status_code, 200)

    def test_origin_csrf_and_host_restrictions(self):
        self.assertEqual(self.post('/api/login', {}, origin='https://evil.example').status_code, 403)
        self.login()
        self.assertEqual(self.post('/api/upload', {}, csrf='wrong').status_code, 403)
        self.assertEqual(self.post('/api/action', {}, origin='https://evil.example').status_code, 403)
        self.assertEqual(self.client.get('/', base_url='https://evil.example').status_code, 400)
        self.assertEqual(self.client.get('/api/bootstrap', base_url=self.settings['PUBLIC_ORIGIN']).status_code, 403)

    def test_logout_revokes_copied_session(self):
        self.login()
        cookie = self.client.get_cookie('bmd_session', domain='desk.example').value
        self.assertEqual(self.get('/api/bootstrap').status_code, 200)
        self.assertEqual(self.post('/api/logout', {}).status_code, 200)
        self.client.set_cookie('bmd_session', cookie, domain='desk.example')
        self.assertEqual(self.get('/api/bootstrap').status_code, 401)

    def test_login_rate_limit(self):
        for _ in range(20): self.assertEqual(self.post('/api/login', {'access_key': 'wrong'}).status_code, 401)
        self.assertEqual(self.post('/api/login', {'access_key': 'wrong'}).status_code, 429)

    def test_bad_json_and_errors_do_not_disclose_secrets(self):
        self.login()
        self.assertEqual(self.post('/api/login', []).status_code, 400)
        self.assertEqual(self.post('/api/action', []).status_code, 400)
        with patch.object(self.app.extensions['engine'], 'post', side_effect=RuntimeError('PRIVATE-SECRET')):
            response = self.post('/api/action', {})
            self.assertEqual(response.status_code, 400)
            self.assertNotIn('PRIVATE-SECRET', response.get_data(as_text=True))

    def test_paper_flow_and_restart_persistence(self):
        self.login()
        body = dict(action='budget', params={}, workspace='practice', simulation=True)
        self.assertEqual(len(self.post('/api/action', body).json['orders']), 4)
        app2 = create_app(self.settings)
        client2 = app2.test_client()
        cookie = self.client.get_cookie('bmd_session', domain='desk.example').value
        client2.set_cookie('bmd_session', cookie, domain='desk.example')
        self.assertEqual(client2.get('/api/bootstrap', base_url=self.settings['PUBLIC_ORIGIN']).status_code, 401)
        saved = app2.extensions['engine'].bootstrap('practice', 'test')
        self.assertEqual(len(saved['documents']['orders']['orders']), 4)
        self.assertEqual(app2.extensions['engine'].snapshot_dir, Path(self.temp.name) / 'snapshots')

    def test_session_expiry_and_callback(self):
        self.login()
        engine = self.app.extensions['engine']
        self.post('/api/auth/kite/start', dict(api_key='synthetic-key', api_secret='synthetic-secret'))
        response = self.get('/kite/callback?request_token=not-real&it_state=wrong')
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['Location'], '/#brokers')
        self.assertFalse(self.get('/api/bootstrap').json['auth_notice']['ok'])
        for record in engine.sessions.values(): record['expires'] = 0
        self.assertEqual(self.get('/api/bootstrap').status_code, 401)
        self.assertFalse(engine.pending)

    def test_headers_and_source_files_not_exposed(self):
        response = self.get('/')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
        response.close()
        for path in ['/india_trader/cloud.py', '/credentials/kite.fernet', '/assets/../../requirements.txt']:
            self.assertEqual(self.get(path).status_code, 404)
        self.login()
        self.assertEqual(self.post('/api/shutdown', {}).status_code, 403)

    def test_production_cookie_flags(self):
        with patch('india_trader.cloud.threading.Thread'):
            app = create_app({**self.settings, 'TESTING': False, 'PERSISTENT_STORAGE_CONFIRMED': 'true'})
        response = app.test_client().post('/api/login', base_url=self.settings['PUBLIC_ORIGIN'], headers={'Origin': self.settings['PUBLIC_ORIGIN']}, json={'access_key': self.settings['APP_ACCESS_KEY']})
        for expected in ['__Host-bmd_session=', 'Secure', 'HttpOnly', 'SameSite=Lax', 'Path=/']:
            self.assertIn(expected, response.headers['Set-Cookie'])
        self.assertIn('max-age=', response.headers['Strict-Transport-Security'])

    def test_vault_encryption_persistence_and_tamper_detection(self):
        root = Path(self.temp.name) / 'vault'
        vault = EncryptedVault(root, self.settings['CREDENTIAL_ENCRYPTION_KEY'])
        values = dict(api_key='synthetic-key', access_token='synthetic-token')
        vault.save('kite', values)
        self.assertNotIn(b'synthetic-token', vault.path('kite').read_bytes())
        self.assertEqual(EncryptedVault(root, self.settings['CREDENTIAL_ENCRYPTION_KEY']).load('kite'), values)
        with self.assertRaises(BrokerError): EncryptedVault(root, 'wrong-' * 10).load('kite')
        vault.path('kite').write_bytes(b'tampered')
        with self.assertRaises(BrokerError): vault.load('kite')
        vault.forget('kite')
        self.assertFalse(vault.status('kite')['encrypted_credentials_saved'])


if __name__ == '__main__': unittest.main()
