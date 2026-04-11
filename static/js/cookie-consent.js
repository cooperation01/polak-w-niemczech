(function () {
  'use strict';

  var COOKIE_KEY = 'cookie_consent_polak_de';

  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? match[2] : null;
  }

  function setCookie(name, value, days) {
    var expires = new Date(Date.now() + days * 864e5).toUTCString();
    document.cookie = name + '=' + value + '; expires=' + expires + '; path=/; SameSite=Strict';
  }

  // Cookie banner
  var banner = document.getElementById('cookie-banner');
  if (banner) {
    if (!getCookie(COOKIE_KEY)) {
      banner.classList.add('visible');
    }

    var acceptBtn = document.getElementById('cookie-accept');
    if (acceptBtn) {
      acceptBtn.addEventListener('click', function () {
        setCookie(COOKIE_KEY, 'accepted', 365);
        banner.classList.remove('visible');
      });
    }
  }

  // Mobile nav toggle
  var toggle = document.querySelector('.nav-toggle');
  var navList = document.querySelector('.nav-list');
  if (toggle && navList) {
    toggle.addEventListener('click', function () {
      var isOpen = navList.classList.toggle('open');
      toggle.setAttribute('aria-expanded', isOpen.toString());
      toggle.setAttribute('aria-label', isOpen ? 'Zamknij menu' : 'Otwórz menu');
    });

    // Close menu on outside click
    document.addEventListener('click', function (e) {
      if (!toggle.contains(e.target) && !navList.contains(e.target)) {
        navList.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });
  }
})();
