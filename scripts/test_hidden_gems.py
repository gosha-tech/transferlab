#!/usr/bin/env python3
"""Regression tests for valuation provenance, age limits and site injection."""
import datetime as dt
import json
import pathlib
import re
import tempfile
import unittest
from unittest import mock

import hidden_gems as gems


class HiddenGemsTests(unittest.TestCase):
    TODAY = dt.date(2026, 11, 22)

    def test_age_boundaries_and_bad_dates(self):
        self.assertEqual(gems.age_on('2003-11-22', self.TODAY), 23)
        self.assertEqual(gems.age_on('2002-11-21', self.TODAY), 24)
        self.assertEqual(gems.age_on('2003-11-23', self.TODAY), 22)
        self.assertIsNone(gems.age_on('not-a-date', self.TODAY))
        self.assertIsNone(gems.age_on('2027-02-01', self.TODAY))

    def test_licensing_identity_timestamp_and_budget_limits(self):
        valid = {'value_eur': 15000000, 'as_of': '2026-11-20',
                 'source':'Verified provider','source_url':'https://example.com/value',
                 'identity_verified':True}
        records = {'price-at-limit':valid,
                   'over-limit':{**valid,'value_eur':15000001},
                   'stale':{**valid,'as_of':'2026-06-08'},
                   'future':{**valid,'as_of':'2026-11-23'},
                   'unverified':{**valid,'identity_verified':False},
                   'bad-number':{**valid,'value_eur':True},
                   'bad-link':{**valid,'source_url':'javascript:alert(1)'}}
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d)/'market.json'
            path.write_text(json.dumps({'schema_version':1,'commercial_rights_checked':False,
                                        'players':records}))
            with mock.patch.object(gems,'MARKET',path):
                self.assertEqual(gems.load_market(self.TODAY)[0],{})
                path.write_text(json.dumps({'schema_version':1,'commercial_rights_checked':True,
                                            'players':records}))
                accepted, rejected = gems.load_market(self.TODAY)
        self.assertIn('price-at-limit',accepted)
        self.assertIn('over-limit',accepted)  # Filtering is a UI concern.
        self.assertNotIn('stale',accepted)
        self.assertNotIn('future',accepted)
        self.assertNotIn('unverified',accepted)
        self.assertNotIn('bad-number',accepted)
        self.assertNotIn('bad-link',accepted)
        self.assertEqual(rejected,5)

    def test_injection_preserves_players_and_ignores_frozen_archive(self):
        root={'players':[{'id':'p1','birth':'2003-11-22','league':'Primeira Liga'}],
              'liveIndexStats':{'2026/27':{'p1':{'minutes':500}}},
              'marketHistory5Y':{'p1':[['2026-06-08',12.0]]}}
        page=('<html><head></head><body><script id="embeddedData" type="application/json">'+
              json.dumps(root)+'</script>'+
              '<aside class="sidebar"><nav class="nav">'+
              '<button id="navCatalog" type="button"><span>Player database</span></button>'+
              '<button id="navFavorites" type="button">Favorites</button>'+
              '</nav></aside>'+
              gems.SECTION_ANCHOR+'catalog</section>'+
              '<script>function showView(){} \n'+gems.MARKER+' }</script></body></html>')
        with tempfile.TemporaryDirectory() as d:
            path=pathlib.Path(d)/'market.json'
            path.write_text(json.dumps({'schema_version':1,
                          'commercial_rights_checked':False,'players':{}}))
            with mock.patch.object(gems,'MARKET',path):
                built,report=gems.inject(page,self.TODAY)
        self.assertIn('id="viewGems"',built)
        # Hidden Gems is part of initial HTML, so users see the navigation
        # without waiting for a deferred script or DOMContentLoaded.
        self.assertIn('id="navGems"',built)
        self.assertIn('class="nav-label">Hidden Gems</span>',built)
        self.assertEqual(built.count('id="navGems"'),1)
        self.assertLess(built.index('id="navCatalog"'),built.index('id="navGems"'))
        self.assertLess(built.index('id="navGems"'),built.index('id="navFavorites"'))
        self.assertIn('window.TransferLabGemsBridge',built)
        self.assertIn('assets/hidden_gems.js',built)
        self.assertIn('assets/hidden_gems.css',built)
        embedded=json.loads(re.search(r'id="embeddedData" type="application/json">(.*?)</script>',
                                     built,re.S).group(1))
        self.assertEqual(len(embedded['players']),1)
        self.assertEqual(embedded['hiddenGemsMarket'],{})
        self.assertEqual(embedded['marketHistory5Y'],root['marketHistory5Y'])
        self.assertEqual(report['young_players_with_450_current_minutes'],1)
        self.assertEqual(report['with_fresh_value_under_15m_and_450_minutes'],0)
        with self.assertRaises(RuntimeError):
            gems.inject(built,self.TODAY)


if __name__=='__main__':
    unittest.main(verbosity=2)
