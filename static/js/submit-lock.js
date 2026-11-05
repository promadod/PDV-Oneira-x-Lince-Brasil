/**
 * OneiraSubmitLock — evita cliques/envios duplicados em rede lenta.
 * - lock()/unlock() para AJAX
 * - captura automática de forms method=POST (opt-out: data-submit-lock="off")
 */
(function (window, document) {
  'use strict';

  var locked = false;
  var overlay = null;
  var msgEl = null;
  var lockedButtons = [];

  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.getElementById('oneira-submit-lock');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'oneira-submit-lock';
      overlay.setAttribute('role', 'alertdialog');
      overlay.setAttribute('aria-live', 'assertive');
      overlay.setAttribute('aria-busy', 'true');
      overlay.innerHTML =
        '<div class="oneira-submit-lock-card">' +
          '<div class="oneira-submit-lock-spinner" aria-hidden="true"></div>' +
          '<p class="oneira-submit-lock-msg">Salvando…</p>' +
          '<p class="oneira-submit-lock-sub">Aguarde, não clique novamente</p>' +
        '</div>';
      document.body.appendChild(overlay);
    }
    msgEl = overlay.querySelector('.oneira-submit-lock-msg');
    return overlay;
  }

  function disableFormButtons(form) {
    if (!form) return;
    var nodes = form.querySelectorAll('button[type="submit"], input[type="submit"], button:not([type]), button[type="button"].btn-modal-confirmar');
    nodes.forEach(function (btn) {
      if (btn.disabled) return;
      btn.disabled = true;
      btn.classList.add('oneira-btn-locked');
      lockedButtons.push(btn);
    });
  }

  function restoreButtons() {
    lockedButtons.forEach(function (btn) {
      btn.disabled = false;
      btn.classList.remove('oneira-btn-locked');
    });
    lockedButtons = [];
  }

  function lock(message, form) {
    if (locked) return false;
    locked = true;
    ensureOverlay();
    if (msgEl && message) msgEl.textContent = message;
    else if (msgEl) msgEl.textContent = 'Salvando…';
    overlay.classList.add('ativo');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('oneira-submit-locked');
    if (form) disableFormButtons(form);
    return true;
  }

  function unlock() {
    locked = false;
    if (overlay) {
      overlay.classList.remove('ativo');
      overlay.setAttribute('aria-hidden', 'true');
    }
    document.body.classList.remove('oneira-submit-locked');
    restoreButtons();
  }

  function isLocked() {
    return locked;
  }

  function newKey() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    return 'idemp-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12);
  }

  function isPostForm(form) {
    if (!(form instanceof HTMLFormElement)) return false;
    var method = (form.getAttribute('method') || 'GET').toUpperCase();
    return method === 'POST';
  }

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!isPostForm(form)) return;
    if (form.dataset.submitLock === 'off') return;
    if (e.defaultPrevented) return;

    if (form.dataset.submitting === '1' || locked) {
      e.preventDefault();
      e.stopPropagation();
      return;
    }

    form.dataset.submitting = '1';
    var label = form.dataset.submitLockMsg || 'Salvando…';
    lock(label, form);
  }, false);

  window.OneiraSubmitLock = {
    lock: lock,
    unlock: unlock,
    isLocked: isLocked,
    newKey: newKey,
  };
})(window, document);
