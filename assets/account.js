/* TransferLab account & history. No user identifiers are sent to the
   analytics provider. Browsing works entirely without registration. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const cfg = window.TransferLabAccountConfig || {};
  const key = 'transferlab:recent-players:v1';
  const maxRows = 60;
  let bridge, user = null, client = null, entries = [], pending = false;
  let memory = [];
  const esc = v => String(v ?? '').replace(/[&<>"']/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const normId = v => String(v ?? '').trim().slice(0,128);
  const validTime = v => {
    const t = Date.parse(v || '');
    return Number.isFinite(t) && t > 0 && t <= Date.now()+60000;
  };
  function saved() {
    try { return JSON.parse(localStorage.getItem(key) || '[]'); }
    catch (_) { return memory; }
  }
  function clean(records) {
    const seen = new Set();
    return (Array.isArray(records) ? records : [])
      .filter(r => r && typeof r.player_id === 'string' &&
        r.player_id.length > 0 && r.player_id.length <= 128 &&
        validTime(r.viewed_at) && !!bridge?.getPlayer(r.player_id))
      .sort((a,b) => Date.parse(b.viewed_at)-Date.parse(a.viewed_at))
      .filter(r => {
        if (seen.has(r.player_id)) return false;
        seen.add(r.player_id); return true;
      }).slice(0,maxRows);
  }
  function store() {
    memory = entries.slice();
    try { localStorage.setItem(key,JSON.stringify(entries)); }
    catch (_) { /* Browser storage blocked: session-only history. */ }
  }
  function setStatus(message) {
    const el=$('tlAccountStatus');
    if(el)el.textContent=message;
  }
  function render() {
    if (!$('tlHistoryItems')) return;
    const host=$('tlHistoryItems');
    host.innerHTML=entries.slice(0,40).map(r => {
      const p=bridge.getPlayer(r.player_id);
      if(!p)return '';
      const date=new Date(r.viewed_at).toLocaleString('ru-RU',{
        day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'
      });
      return '<button type="button" class="tl-history-card" data-tl-player="'+
        esc(r.player_id)+'"><span class="tl-history-initial">'+
        esc(p.name?.trim()?.[0]||'•')+'</span><span class="tl-history-details">'+
        '<strong>'+esc(p.name)+'</strong><small>'+esc(p.team||'Клуб не указан')+
        ' · '+esc(p.league||'—')+'</small></span><time datetime="'+
        esc(r.viewed_at)+'">'+esc(date)+'</time></button>';
    }).join('');
    $('tlHistoryInfo').textContent=entries.length?
      'Последние '+entries.length+' профилей · '+(user?
        'синхронизация с аккаунтом':'сохранено на этом устройстве'):
      'История ещё пуста. Откройте карточку любого футболиста.';
    host.querySelectorAll('[data-tl-player]').forEach(button =>
      button.addEventListener('click',() => bridge.openPlayer(button.dataset.tlPlayer)));
    $('tlHistoryClear').disabled=!entries.length;
  }
  function enterHistory() {
    bridge.showCatalog();
    $('viewCatalog')?.classList.add('hidden');
    $('viewAccount')?.classList.remove('hidden');
    $('navCatalog')?.classList.remove('active');
    $('navCatalog')?.setAttribute('aria-current','false');
    $('navAccount').classList.add('active');
    $('navAccount').setAttribute('aria-current','page');
    render();
  }
  async function syncOne(record) {
    if (!client || !user || !record) return;
    const {error}=await client.from('player_history').upsert({
      user_id:user.id,player_id:record.player_id,viewed_at:record.viewed_at
    },{onConflict:'user_id,player_id'});
    if(error)console.warn('TransferLab history sync:',error.message);
  }
  function recordPlayer(id) {
    const pid=normId(id);
    if (!pid || !bridge.getPlayer(pid)) return;
    const row={player_id:pid,viewed_at:new Date().toISOString()};
    entries=clean([row,...entries]);
    store();
    render();
    if(user)void syncOne(row);
  }
  async function restoreCloud(session) {
    if(!client)return;
    if(!session?.user){
      user=null;
      $('tlAccountLogout').hidden=true;
      $('tlAccountForm').hidden=false;
      setStatus('История сохраняется на этом устройстве. Войдите, чтобы сохранить её в аккаунте.');
      render();
      return;
    }
    user=session.user;
    $('tlAccountLogout').hidden=false;
    $('tlAccountForm').hidden=true;
    setStatus('Вы вошли: '+(user.email||'аккаунт')+'. Синхронизируем историю…');
    const owner=user.id;
    // Store any anonymous local activity on first sign-in.
    const local=clean(entries);
    if(local.length){
      const {error}=await client.from('player_history').upsert(
        local.map(r=>({...r,user_id:owner})),{onConflict:'user_id,player_id'});
      if(error)console.warn('TransferLab history import:',error.message);
    }
    const {data,error}=await client.from('player_history')
      .select('player_id,viewed_at').eq('user_id',owner)
      .order('viewed_at',{ascending:false}).limit(maxRows);
    if(user?.id!==owner)return;
    if(error){
      setStatus('Аккаунт подключён, но историю не удалось загрузить. Проверьте права базы данных.');
      console.warn('TransferLab history load:',error.message);
      return;
    }
    entries=clean([...(data||[]),...local]);
    store();render();
    setStatus('Вы вошли: '+(user.email||'аккаунт')+
      '. История сохраняется в вашем аккаунте.');
  }
  function loadSdk() {
    return new Promise((resolve,reject)=>{
      if(window.supabase?.createClient){resolve(window.supabase);return;}
      const script=document.createElement('script');
      script.src='https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.119.2/dist/umd/supabase.min.js';
      script.defer=true;
      script.onload=()=>window.supabase?.createClient?
        resolve(window.supabase):reject(new Error('Supabase SDK не загрузился'));
      script.onerror=()=>reject(new Error('Сервис входа недоступен'));
      document.head.appendChild(script);
    });
  }
  async function setupAuth() {
    const url=String(cfg.supabaseUrl||'');
    const key=String(cfg.supabasePublishableKey||'');
    if(!url || !key) {
      $('tlAccountForm').hidden=true;
      $('tlAccountLogout').hidden=true;
      setStatus('История работает на этом устройстве. Регистрация появится после подключения сервиса аккаунтов.');
      return;
    }
    $('tlAccountForm').hidden=false;
    setStatus('Войдите по email, чтобы сохранять историю между устройствами.');
    try {
      const sdk=await loadSdk();
      client=sdk.createClient(url,key,{
        auth:{autoRefreshToken:true,persistSession:true,detectSessionInUrl:true}
      });
      client.auth.onAuthStateChange((_event,session)=>{
        // Do not call the Supabase API synchronously inside the auth callback.
        setTimeout(()=>{void restoreCloud(session);},0);
      });
      const {data,error}=await client.auth.getSession();
      if(error)throw error;
      await restoreCloud(data?.session);
    }catch(error) {
      setStatus('Сервис регистрации сейчас недоступен; история остаётся в этом браузере.');
      console.warn('TransferLab sign-in init:',error.message||error);
    }
  }
  async function sendLink() {
    if(!client || pending)return;
    const email=$('tlAccountEmail').value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length>254){
      setStatus('Проверьте адрес электронной почты.');return;
    }
    pending=true;
    $('tlAccountSend').disabled=true;
    try {
      const redirect=location.origin+location.pathname;
      const {error}=await client.auth.signInWithOtp({
        email,options:{emailRedirectTo:redirect,shouldCreateUser:true}
      });
      if(error)throw error;
      setStatus('Если адрес доступен для регистрации, письмо со ссылкой отправлено. Проверьте почту.');
    }catch(error) {
      setStatus('Не удалось отправить ссылку: '+String(error.message||error));
    }finally{
      pending=false;
      $('tlAccountSend').disabled=false;
    }
  }
  async function signOut() {
    if(!client)return;
    const {error}=await client.auth.signOut();
    if(error){setStatus('Не удалось выйти: '+error.message);return;}
    user=null;
    // Don't reveal the previous account's synchronized history to the next
    // visitor using the same device. Start a fresh anonymous history.
    entries=[];store();render();
    setStatus('Вы вышли. Новые просмотры будут сохраняться только на этом устройстве.');
  }
  async function clearHistory() {
    if(!entries.length)return;
    if(!confirm('Очистить всю историю просмотренных игроков'+
      (user?' в аккаунте и на этом устройстве':' на этом устройстве')+'?'))return;
    if(user&&client){
      const {error}=await client.from('player_history')
        .delete().eq('user_id',user.id);
      if(error){
        setStatus('Не удалось очистить историю аккаунта: '+error.message);
        return;
      }
    }
    entries=[];store();render();
  }
  function init() {
    bridge=window.TransferLabAccountBridge;
    if(!bridge || !$('navAccount') || !$('viewAccount'))return;
    entries=clean(saved());
    store();render();
    $('navAccount').addEventListener('click',enterHistory);
    $('tlHistoryClear').addEventListener('click',()=>{void clearHistory();});
    $('tlAccountForm').addEventListener('submit',event=>{
      event.preventDefault();void sendLink();
    });
    $('tlAccountLogout').addEventListener('click',()=>{void signOut();});
    document.addEventListener('transferlab:player-opened',event=>
      recordPlayer(event.detail?.playerId));
    void setupAuth();
    window.TransferLabAccountDebug=Object.freeze({enabled:!!cfg.supabaseUrl,historyCount:()=>entries.length});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
