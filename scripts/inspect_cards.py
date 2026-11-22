#!/usr/bin/env python3
from pathlib import Path
from zipfile import ZipFile
import re
html=ZipFile(Path(__file__).resolve().parents[1]/'TransferLab_RESTORED_2026-11-16.zip').read('index.html').decode('utf-8')
terms=['function cardHTML(', 'function playerCard(', 'function renderCard(', 'function renderCatalog(', 'function cardMarkup(', 'function contract(', 'function projectedIndex(', 'function roleFor(', 'const FORMULA_DRAFT=', 'Контракт до ', 'goals+assists','goals} гол']
for term in terms:
    at=html.find(term)
    print('\nDIAG',term,at)
    if at>=0:
        print(html[at:at+(7500 if term in ('function renderCard(', 'function cardHTML(', 'function playerCard(', 'function renderCatalog(', 'function projectedIndex(') else 2000)])
for m in re.finditer(r'(?i)(function\s+\w*[Cc]ard\w*\(|function\s+\w*[Ii]ndex\w*\(|contract.*?textContent|contract.*?<span)',html):
    print('MORE',m.start(),html[max(0,m.start()-120):m.start()+800].replace('\n',' '))

for term in ['function attachPhoto(', 'function photoCandidates(', 'function resolvePhoto(', 'function ensurePhoto(', 'function photoSources(', 'function storedPhoto(']:
  at=html.find(term)
  print('IMAGE FUNC',term,at)
  if at>=0: print(html[at:at+6200])

for term in ['statStarts','Старты','Starts','statGoals']:
  at=html.find(term)
  print('UI STAT LABEL',term,at,repr(html[max(0,at-500):at+480]))
