(function () {
  const p = location.pathname.replace(/\/$/, '') || '/';
  const id = {
    '/': 'nav-3d',
    '/flat': 'nav-flat',
    '/bus': 'nav-bus',
    '/house': 'nav-house',
    '/graph': 'nav-graph',
    '/attractors': 'nav-attr'
  }[p];
  if (id) document.getElementById(id).classList.add('on');
})();
