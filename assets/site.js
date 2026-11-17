// TransferLab: lightweight progressive enhancements, no calls to remote APIs in browsers.
(() => {
  document.querySelectorAll('[data-view]').forEach(button => {
    const sync=()=>document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-current',b.classList.contains('active')?'page':'false'));
    button.addEventListener('click',sync);
    sync();
  });
  const search=document.getElementById('search');
  if(search)search.setAttribute('aria-autocomplete','list');

  function matchBoard(){
    const panel=document.getElementById('freeMatchesPanel');
    const selector=document.getElementById('freeMatchLeague');
    const host=document.getElementById('freeMatchRows');
    const attribution=document.getElementById('freeMatchSource');
    const json=document.getElementById('embeddedData');
    if(!panel||!selector||!host||!json)return;
    let root;
    try{root=JSON.parse(json.textContent);}catch{return}
    const rows=root.freeMatchResults||{};
    const leagues=Object.keys(rows).filter(k=>Array.isArray(rows[k])&&rows[k].length).sort((a,b)=>a.localeCompare(b,'ru'));
    selector.textContent='';
    for(const league of leagues){
      const opt=document.createElement('option');opt.value=league;opt.textContent=league;selector.append(opt);
    }
    if(!leagues.length){
      host.textContent='Нет подтверждённых свежих результатов: загрузка источников ещё не завершена.';
      attribution.textContent='Ни одного доступного источника';
      panel.open=false;
      return;
    }
    function render(){
      const matches=rows[selector.value]||[];
      host.textContent='';
      for(const entry of matches.slice(0,10)){
        if(!entry||!entry.date)continue;
        const line=document.createElement('div');line.className='free-match-row';
        const date=document.createElement('span');date.className='free-match-date';date.textContent=entry.date;
        const teams=document.createElement('span');teams.className='free-match-teams';
        teams.textContent=(entry.home||'')+' — '+(entry.away||'');
        const score=document.createElement('strong');score.className='free-match-score';
        score.textContent=entry.home_goals+' : '+entry.away_goals;
        line.append(date,teams,score);
        host.append(line);
      }
      attribution.textContent='Источник: '+(matches[0]?.provider||'')+' · последний матч '+(matches[0]?.date||'');
    }
    selector.addEventListener('change',render);render();
  }
  matchBoard();
})();
