"""Isolated regression tests for account injection and public-only configuration."""
import json
import os
import unittest
from unittest import mock

from account_build import NAV, inject, public_config, validate_publishable_key


def fixture():
    return (
        '<html><head></head><body>'
        '<div class="sidebar"><nav>'
        '<button id="navCatalog">Catalog</button>'
        '<button id="navFavorites">Favorites</button>'
        '</nav></div>'
        '<script>function showView(){} function choosePlayer(){} '
        '  function renderProfile(){} </script>'
        '<section id="viewCatalog" class="hidden">Catalog</section>'
        '</body></html>'
    )


class AccountBuildTests(unittest.TestCase):
    def test_renders_account_in_initial_html(self):
        out = inject(fixture())
        self.assertEqual(out.count('id="navAccount"'), 1)
        self.assertEqual(out.count('id="viewAccount"'), 1)
        self.assertLess(out.index('id="navFavorites"'),out.index('id="navAccount"'))
        self.assertLess(out.index('id="navAccount"'),out.index('id="viewCatalog"'))
        self.assertIn('transferlab:player-opened',out)
        self.assertIn('assets/account.js',out)
        self.assertIn('assets/account.css',out)
        self.assertNotIn('static.cloudflareinsights.com',out)
        self.assertIn('"supabaseUrl":""',out)

    def test_refuses_double_injection(self):
        with self.assertRaises(RuntimeError):
            inject(inject(fixture()))

    def test_analytics_requires_real_token(self):
        out=inject(fixture(),token='0123456789abcdef0123456789abcdef')
        self.assertIn('static.cloudflareinsights.com/beacon.min.js',out)
        self.assertIn('0123456789abcdef0123456789abcdef',out)

    def test_rejects_service_key(self):
        with self.assertRaises(RuntimeError):
            validate_publishable_key('sb_secret_abc123')

    def test_unconfigured_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg,token=public_config()
        self.assertFalse(cfg['analyticsEnabled'])
        self.assertEqual(cfg['supabaseUrl'],'')
        self.assertEqual(token,'')

    def test_rejects_half_configuration(self):
        with mock.patch.dict(os.environ,{'TRANSFERLAB_SUPABASE_URL':'https://sample.supabase.co'},clear=True):
            with self.assertRaises(RuntimeError):
                public_config()

    def test_configured_public_keys_only(self):
        env={'TRANSFERLAB_SUPABASE_URL':'https://sample.supabase.co',
             'TRANSFERLAB_SUPABASE_PUBLISHABLE_KEY':'sb_publishable_abcde12345',
             'TRANSFERLAB_CLOUDFLARE_WEB_ANALYTICS_TOKEN':'0123456789abcdef0123456789abcdef'}
        with mock.patch.dict(os.environ,env,clear=True):
            cfg,token=public_config()
        self.assertEqual(cfg['supabaseUrl'],'https://sample.supabase.co')
        self.assertTrue(cfg['analyticsEnabled'])
        self.assertEqual(token,env['TRANSFERLAB_CLOUDFLARE_WEB_ANALYTICS_TOKEN'])
        out=inject(fixture(),cfg,token)
        self.assertIn('sample.supabase.co',out)

if __name__=='__main__':
    unittest.main(verbosity=2)
