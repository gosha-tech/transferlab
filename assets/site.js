// Progressive enhancement for TransferLab 5.0
(() => {
  document.querySelectorAll('[data-view]').forEach(button => {
    const sync = () => document.querySelectorAll('[data-view]').forEach(b => b.setAttribute('aria-current', b.classList.contains('active') ? 'page' : 'false'));
    button.addEventListener('click', sync); sync();
  });
  const search = document.getElementById('search');
  if(search) search.setAttribute('aria-autocomplete', 'list');
})();
