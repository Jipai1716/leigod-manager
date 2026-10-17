// ==UserScript==
// @name         雷神 Token 提取 → 推送到管理器面板
// @namespace    https://github.com/Jipai1716/leigod-manager
// @version      1.1.0
// @description  在雷神官网登录后一键提取 account_token，可复制，也可直接推送到自建的管理面板
// @author       Jipai
// @match        https://*.leigod.com/*
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_xmlhttpRequest
// @connect      *
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  if (!/(^|\.)leigod\.com$/i.test(location.hostname)) return;

  var KEYS = ['account_token', 'accountToken', 'user_token', 'token'];
  var STORES = ['localStorage', 'sessionStorage'];

  // ---------- 提取 ----------
  function safeGet(store, key) {
    try { return window[store].getItem(key); } catch (e) { return null; }
  }

  function allKeys(store) {
    var out = [];
    try {
      var s = window[store];
      for (var i = 0; i < s.length; i++) out.push(s.key(i));
    } catch (e) {}
    return out;
  }

  function dig(value) {
    if (value == null) return null;
    if (typeof value === 'string') {
      var text = value.trim();
      if (!text) return null;
      if (text.charAt(0) === '{' || text.charAt(0) === '[') {
        try { return dig(JSON.parse(text)); } catch (e) { return null; }
      }
      return text;
    }
    if (typeof value !== 'object') return null;

    var names = ['account_token', 'accountToken', 'token'];
    for (var i = 0; i < names.length; i++) {
      if (value[names[i]] && typeof value[names[i]] === 'string') return value[names[i]];
    }
    if (value.data) return dig(value.data);
    if (value.login_info) return dig(value.login_info);
    return null;
  }

  function extract() {
    for (var s = 0; s < STORES.length; s++) {
      var store = STORES[s];
      for (var k = 0; k < KEYS.length; k++) {
        var token = dig(safeGet(store, KEYS[k]));
        if (token) return { token: token, from: store + '.' + KEYS[k] };
      }
      var keys = allKeys(store);
      for (var i = 0; i < keys.length; i++) {
        var raw = safeGet(store, keys[i]);
        if (typeof raw === 'string' && raw.indexOf('account_token') !== -1) {
          var found = dig(raw);
          if (found) return { token: found, from: store + '.' + keys[i] };
        }
      }
    }
    return null;
  }

  function mask(t) {
    if (!t) return '';
    return t.length <= 12 ? t.slice(0, 3) + '****' : t.slice(0, 6) + '****' + t.slice(-4);
  }

  // ---------- 剪贴板 ----------
  function copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(function () { return true; },
        function () { return legacyCopy(text); });
    }
    return Promise.resolve(legacyCopy(text));
  }

  function legacyCopy(text) {
    try {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;top:-1000px;opacity:0';
      document.body.appendChild(ta);
      ta.select();
      ta.setSelectionRange(0, text.length);
      var ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return ok;
    } catch (e) { return false; }
  }

  // ---------- 面板 ----------
  function panelUrl() {
    var v = (typeof GM_getValue === 'function' ? GM_getValue('panelUrl', '') : '') || '';
    if (!v) {
      v = window.prompt('第一次使用：填写管理器面板地址\n例如 http://<主机IP>:5788', 'http://');
      if (!v || v.indexOf('http') !== 0) return '';
      v = v.replace(/\/+$/, '');
      if (typeof GM_setValue === 'function') GM_setValue('panelUrl', v);
    }
    return v;
  }

  function pushToPanel(base, token) {
    return new Promise(function (resolve, reject) {
      var payload = JSON.stringify({ token: token });
      if (typeof GM_xmlhttpRequest === 'function') {
        GM_xmlhttpRequest({
          method: 'POST',
          url: base + '/api/token',
          headers: { 'Content-Type': 'application/json' },
          data: payload,
          timeout: 15000,
          onload: function (r) {
            try { resolve(JSON.parse(r.responseText)); }
            catch (e) { reject(new Error('返回不是 JSON: ' + r.responseText.slice(0, 80))); }
          },
          onerror: function () { reject(new Error('请求失败，检查面板地址与网络')); },
          ontimeout: function () { reject(new Error('请求超时')); }
        });
      } else {
        fetch(base + '/api/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload
        }).then(function (r) { return r.json(); }).then(resolve).catch(reject);
      }
    });
  }

  // ---------- UI ----------
  var toastTimer = null;
  function toast(msg, ok) {
    var box = document.getElementById('lg-toast');
    if (!box) {
      box = document.createElement('div');
      box.id = 'lg-toast';
      box.style.cssText = [
        'position:fixed', 'left:50%', 'transform:translateX(-50%)', 'bottom:120px',
        'max-width:82vw', 'padding:10px 14px', 'border-radius:8px', 'font-size:13px',
        'line-height:1.5', 'color:#fff', 'z-index:2147483647',
        'box-shadow:0 4px 16px rgba(0,0,0,.28)', 'word-break:break-all',
        'white-space:pre-wrap', 'font-family:-apple-system,BlinkMacSystemFont,sans-serif'
      ].join(';');
      document.body.appendChild(box);
    }
    box.style.background = ok ? 'rgba(22,163,74,.95)' : 'rgba(220,38,38,.95)';
    box.textContent = msg;
    box.style.display = 'block';
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { box.style.display = 'none'; }, 4200);
  }

  function makeButton(id, text, bottom, bg) {
    var b = document.createElement('div');
    b.id = id;
    b.textContent = text;
    b.style.cssText = [
      'position:fixed', 'right:14px', 'bottom:' + bottom + 'px', 'z-index:2147483646',
      'padding:8px 12px', 'border-radius:18px', 'background:' + bg, 'color:#fff',
      'font-size:13px', 'font-family:-apple-system,BlinkMacSystemFont,sans-serif',
      'box-shadow:0 3px 10px rgba(0,0,0,.3)', 'user-select:none', 'cursor:pointer',
      'opacity:.94'
    ].join(';');
    return b;
  }

  function build() {
    if (document.getElementById('lg-btn-copy')) return;

    var btnCopy = makeButton('lg-btn-copy', '提取 Token', 150, 'rgba(17,24,39,.9)');
    btnCopy.onclick = function () {
      var r = extract();
      if (!r) { toast('未检测到登录状态\n请先登录雷神官网', false); return; }
      copy(r.token).then(function (ok) {
        if (ok) toast('已复制 ' + mask(r.token) + '\n来源 ' + r.from, true);
        else { toast('自动复制失败，请手动复制', false); window.prompt('手动复制', r.token); }
      });
    };

    var btnPush = makeButton('lg-btn-push', '推送到面板', 98, 'rgba(37,99,235,.92)');
    btnPush.onclick = function () {
      var r = extract();
      if (!r) { toast('未检测到登录状态\n请先登录雷神官网', false); return; }
      var base = panelUrl();
      if (!base) return;
      btnPush.textContent = '推送中…';
      pushToPanel(base, r.token).then(function (res) {
        if (res && res.ok) toast('已推送到面板\n' + (res.text || '').replace(/\n/g, ' '), true);
        else toast('推送失败：' + ((res && (res.text || res.error)) || '未知错误'), false);
      }).catch(function (e) {
        toast('推送失败：' + e.message, false);
      }).then(function () {
        btnPush.textContent = '推送到面板';
      });
    };

    document.body.appendChild(btnCopy);
    document.body.appendChild(btnPush);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build);
  } else {
    build();
  }
})();
