/* TransferLab Bug Hunt — static, privacy-preserving issue composer.
 * No external telemetry or automatic submission; visitors explicitly open GitHub
 * or copy the report to share without a GitHub account.
 */
(() => {
  'use strict';
  const ROOT='https://github.com/gosha-tech/transferlab/issues/new';
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const ui={
    ru:{
      trigger:'Нашли ошибку?',title:'Сообщить об ошибке',subtitle:'Помогите проверить TransferLab. Сообщение не отправляется автоматически.',
      type:'Тип проблемы',player:'Игрок (если ошибка в профиле)',observed:'Что неправильно?',expected:'Как должно быть?',source:'Источник корректных данных (ссылка)',url:'Страница',notes:'Не прикладывайте личные данные. Сообщения GitHub Issues публичны.',
      copy:'Скопировать отчёт',open:'Открыть отчёт в GitHub',close:'Закрыть',
      copied:'Отчёт скопирован. Передайте его организатору тестирования.',
      selected:'Не удалось скопировать автоматически — выделен текст отчёта, нажмите Ctrl+C / ⌘C.',
      invalid:'Опишите проблему, чтобы подготовить отчёт.',
      needsLogin:'GitHub потребует вход. Без GitHub можно скопировать отчёт и отправить организатору.',
      guide:'Как участвовать в Bug Hunt',choose:'Выберите',
      types:['Неверная статистика','Неверный клуб или позиция','Индекс или рыночная стоимость','Hidden Gems','Фотография','Интерфейс или скорость','Другое']
    },
    en:{
      trigger:'Report a bug',title:'Report an issue',subtitle:'Help verify TransferLab. Nothing is submitted automatically.',
      type:'Issue type',player:'Player (if applicable)',observed:'What is wrong?',expected:'What should be correct?',source:'Evidence / source URL',url:'Page',notes:'Do not share private information. GitHub Issues are public.',
      copy:'Copy report',open:'Open report on GitHub',close:'Close',
      copied:'Report copied. Share it with the beta-test organizer.',
      selected:'Automatic copy failed — report text selected. Press Ctrl+C / ⌘C.',
      invalid:'Describe the problem to prepare a report.',
      needsLogin:'GitHub requires sign-in. Without GitHub, copy the report and share it with the organizer.',
      guide:'How to join the Bug Hunt',choose:'Choose',
      types:['Incorrect statistics','Wrong club or position','Index or market valuation','Hidden Gems','Player portrait','UI or performance','Other']
    }
  };
  const labels=()=>{
    const en=document.documentElement.lang.toLowerCase().startsWith('en');
    return en?ui.en:ui.ru;
  };
  const html='<button type="button" id="tlBugTrigger" class="tl-bug-trigger" aria-haspopup="dialog"></button>'+
    '<dialog id="tlBugDialog" class="tl-bug-dialog" aria-labelledby="tlBugTitle">'+
      '<div class="tl-bug-head"><div><strong id="tlBugTitle"></strong><p id="tlBugSubtitle"></p></div>'+
      '<button id="tlBugClose" type="button" class="tl-bug-close" aria-label="Close">×</button></div>'+
      '<form id="tlBugForm" novalidate>'+
       '<label for="tlBugType" id="tlBugTypeLabel"></label>'+
       '<select id="tlBugType" required></select>'+
       '<label for="tlBugPlayer" id="tlBugPlayerLabel"></label>'+
       '<input id="tlBugPlayer" name="player" autocomplete="off" maxlength="160" placeholder="Name / Имя игрока">'+
       '<label for="tlBugObserved" id="tlBugObservedLabel"></label>'+
       '<textarea id="tlBugObserved" required rows="3" minlength="5" maxlength="1300"></textarea>'+
       '<label for="tlBugExpected" id="tlBugExpectedLabel"></label>'+
       '<textarea id="tlBugExpected" rows="2" maxlength="700"></textarea>'+
       '<label for="tlBugEvidence" id="tlBugEvidenceLabel"></label>'+
       '<input id="tlBugEvidence" type="url" inputmode="url" placeholder="https://" maxlength="400">'+
       '<p class="tl-bug-page"><span id="tlBugPageLabel"></span>: <span id="tlBugPage"></span></p>'+
       '<p class="tl-bug-disclosure" id="tlBugDisclosure"></p>'+
       '<p class="tl-bug-status" id="tlBugStatus" role="status" aria-live="polite"></p>'+
       '<div class="tl-bug-actions">'+
       '<button id="tlBugCopy" type="button" class="tl-bug-copy"></button>'+
       '<a id="tlBugOpen" class="tl-bug-open" href="'+ROOT+'" target="_blank" rel="noopener noreferrer"></a>'+
       '</div>'+
       '<p class="tl-bug-login" id="tlBugLogin"></p>'+
       '<a id="tlBugGuide" class="tl-bug-guide" href="bughunt.html"></a>'+
      '</form>'+
    '</dialog>';
  document.body.insertAdjacentHTML('beforeend',html);
  const $=id=>document.getElementById(id);
  const trigger=$('tlBugTrigger'),dialog=$('tlBugDialog'),status=$('tlBugStatus');
  const types=['statistics','club_position','index_value','hidden_gems','portrait','ui_performance','other'];
  function language(){
    const t=labels();
    trigger.textContent='🐞 '+t.trigger;
    trigger.title=t.trigger;
    $('tlBugTitle').textContent=t.title;
    $('tlBugSubtitle').textContent=t.subtitle;
    for(const [id,key] of [
      ['tlBugTypeLabel','type'],['tlBugPlayerLabel','player'],
      ['tlBugObservedLabel','observed'],['tlBugExpectedLabel','expected'],
      ['tlBugEvidenceLabel','source'],['tlBugPageLabel','url'],
      ['tlBugDisclosure','notes'],['tlBugCopy','copy'],['tlBugOpen','open'],
      ['tlBugLogin','needsLogin'],['tlBugGuide','guide'],['tlBugClose','close']
    ]) $(id).textContent=t[key];
    const previous=$('tlBugType').value;
    $('tlBugType').replaceChildren();
    types.forEach((code,i)=>{
      const opt=document.createElement('option');opt.value=code;opt.textContent=t.types[i];
      $('tlBugType').append(opt);
    });
    $('tlBugType').value=previous||types[0];
    $('tlBugClose').setAttribute('aria-label',t.close);
  }
  function playerName(){
    const view=$('viewProfile');
    if(!view||view.classList.contains('hidden'))return '';
    const v=$('pName')?.textContent?.trim()||'';
    return v==='—'?'':v.slice(0,160);
  }
  function report(){
    const t=labels();
    const category=types.indexOf($('tlBugType').value);
    const type=t.types[Math.max(0,category)];
    const player=$('tlBugPlayer').value.trim();
    const observed=$('tlBugObserved').value.trim();
    const expected=$('tlBugExpected').value.trim();
    const source=$('tlBugEvidence').value.trim();
    const url=location.href.split('#')[0];
    const body=[
      '## '+t.type, type,
      '## '+t.player, player||'—',
      '## '+t.observed, observed||'—',
      '## '+t.expected, expected||'—',
      '## '+t.source, source||'—',
      '## URL',url,
      '## Date (UTC)',new Date().toISOString().slice(0,10),
      '',
      '> Community Beta Bug Hunt. Reported data are claims to verify, not confirmed corrections.'
    ].join('\n\n');
    const title='[Beta] '+type+(player?' — '+player:'');
    return {title,body,observed};
  }
  function update(){
    const value=report();
    const url=new URL(ROOT);
    // GitHub's issue creation URL is a native first-party form; no hidden server.
    url.searchParams.set('title',value.title);
    url.searchParams.set('body',value.body);
    $('tlBugOpen').href=url.toString();
    $('tlBugOpen').setAttribute('aria-disabled',String(value.observed.length<5));
  }
  function open(){
    language();
    $('tlBugPlayer').value=playerName();
    $('tlBugObserved').value='';
    $('tlBugExpected').value='';
    $('tlBugEvidence').value='';
    $('tlBugPage').textContent=location.pathname||'/';
    status.textContent='';
    update();
    dialog.showModal();
    $('tlBugType').focus();
  }
  trigger.addEventListener('click',open);
  $('tlBugClose').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()});
  $('tlBugForm').addEventListener('input',()=>{status.textContent='';update()});
  $('tlBugForm').addEventListener('change',update);
  function valid(){
    if(report().observed.length>=5)return true;
    status.textContent=labels().invalid;
    $('tlBugObserved').focus();
    return false;
  }
  $('tlBugOpen').addEventListener('click',e=>{if(!valid())e.preventDefault()});
  $('tlBugCopy').addEventListener('click',async()=>{
    if(!valid())return;
    const value=report().title+'\n\n'+report().body;
    try {
      if(!navigator.clipboard || !navigator.clipboard.writeText)throw Error('Clipboard unavailable');
      await navigator.clipboard.writeText(value);
      status.textContent=labels().copied;
    } catch (_) {
      const textarea=document.createElement('textarea');
      textarea.value=value;
      textarea.className='tl-bug-fallback';
      textarea.setAttribute('aria-label','Copy report manually');
      $('tlBugForm').append(textarea);
      textarea.focus();
      textarea.select();
      status.textContent=labels().selected;
    }
  });
  // When the site language changes, refresh button and form labels too.
  new MutationObserver(()=>{if(!dialog.open)language()}).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
  language();
  update();
})();
