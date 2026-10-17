// ==UserScript==
// @name         雷神官网 Token 提取（Via / 手机浏览器）
// @namespace    https://github.com/Jipai1716/leigod-manager
// @version      1.0.0
// @description  在雷神官网登录后，一键把 account_token 复制到剪贴板，方便发给 QQ Bot
// @author       Jipai
// @match        https://*.leigod.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  // 只在雷神域名下工作
  if (!/(^|\.)leigod\.com$/i.test(location.hostname)) return;

  var CANDIDATE_KEYS = ['account_token', 'accountToken', 'user_token', 'token'];
  var STORAGES = ['localStorage', 'sessionStorage'];

  function safeGet(storeName, key) {
    try {
      return window[storeName].getItem(key);
    } catch (e) {
      return null;
    }
  }

  function allKeys(storeName) {
    var keys = [];
    try {
      var store = window[storeName];
      for (var i = 0; i < store.length; i++) keys.push(store.key(i));
    } catch (e) {
      /* 某些 WebView 不允许枚举，忽略 */
    }
    return keys;
  }

  /** 从任意值里挖出形如 token 的字符串 */
  function dig(value) {
    if (value == null) return null;
    if (typeof value === 'string') {
      var text = value.trim();
      if (!text) return null;
      // 本身就是 JSON？
      if (text.charAt(0) === '{' || text.charAt(0) === '[') {
        try {
          return dig(JSON.parse(text));
        } catch (e) {
          return null;
        }
      }
      return text;
    }
    if (typeof value !== 'object') return null;

    // 常见结构：{ account_token: "..." } 或 { data: { account_token } }
    var names = ['account_token', 'accountToken', 'token'];
    for (var i = 0; i < names.length; i++) {
      if (value[names[i]] && typeof value[names[i]] === 'string') return value[names[i]];
    }
    if (value.data) return dig(value.data);
    if (value.login_info) return dig(value.login_info);
    return null;
  }

  /** 按优先级找 token：先常规 key，再全量扫描包含 account_token 的值 */
  function extractToken() {
    for (var s = 0; s < STORAGES.length; s++) {
      var store = STORAGES[s];
      for (var k = 0; k < CANDIDATE_KEYS.length; k++) {
        var raw = safeGet(store, CANDIDATE_KEYS[k]);
        var token = dig(raw);
        if (token) return { token: token, from: store + '.' + CANDIDATE_KEYS[k] };
      }
      var keys = allKeys(store);
      for (var i = 0; i < keys.length; i++) {
        var value = safeGet(store, keys[i]);
        if (typeof value === 'string' && value.indexOf('account_token') !== -1) {
          var found = dig(value);
          if (found) return { token: found, from: store + '.' + keys[i] };
        }
      }
    }
    return null;
  }

  function mask(token) {
    if (!token) return '';
    if (token.length <= 12) return token.slice(0, 3) + '****';
    return token.slice(0, 6) + '****' + token.slice(-4);
  }

  function copyText(text) {
    // 优先 Clipboard API（需要安全上下文）
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(
        function () {
          return true;
        },
        function () {
          return legacyCopy(text);
        }
      );
    }
    return Promise.resolve(legacyCopy(text));
  }

  function legacyCopy(text) {
    try {
      var area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', 'readonly');
      area.style.position = 'fixed';
      area.style.top = '-1000px';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      area.setSelectionRange(0, area.value.length);
      var ok = document.execCommand('copy');
      document.body.removeChild(area);
      return ok;
    } catch (e) {
      return false;
    }
  }

  var toastTimer = null;
  function toast(message, ok) {
    var box = document.getElementById('leigod-token-toast');
    if (!box) {
      box = document.createElement('div');
      box.id = 'leigod-token-toast';
      box.style.cssText = [
        'position:fixed',
        'left:50%',
        'transform:translateX(-50%)',
        'bottom:110px',
        'max-width:80vw',
        'padding:10px 14px',
        'border-radius:8px',
        'font-size:13px',
        'line-height:1.5',
        'color:#fff',
        'z-index:2147483647',
        'box-shadow:0 4px 16px rgba(0,0,0,.25)',
        'word-break:break-all',
        'white-space:pre-wrap',
        'font-family:-apple-system,BlinkMacSystemFont,sans-serif'
      ].join(';');
      document.body.appendChild(box);
    }
    box.style.background = ok ? 'rgba(22,163,74,.95)' : 'rgba(220,38,38,.95)';
    box.textContent = message;
    box.style.display = 'block';
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      box.style.display = 'none';
    }, 4000);
  }

  function buildButton() {
    var btn = document.createElement('div');
    btn.id = 'leigod-token-btn';
    btn.textContent = '提取 Token';
    btn.style.cssText = [
      'position:fixed',
      'right:14px',
      'bottom:96px',
      'z-index:2147483646',
      'padding:8px 12px',
      'border-radius:18px',
      'background:rgba(17,24,39,.88)',
      'color:#fff',
      'font-size:13px',
      'font-family:-apple-system,BlinkMacSystemFont,sans-serif',
      'box-shadow:0 3px 10px rgba(0,0,0,.3)',
      'user-select:none',
      'cursor:pointer',
      'opacity:.92'
    ].join(';');

    btn.addEventListener('click', function () {
      var result = extractToken();
      if (!result) {
        // 没检测到 → 明确提示，绝不返回伪造 token
        toast('未检测到登录状态\n请先在官网完成登录，再点一次', false);
        return;
      }
      copyText(result.token).then(function (copied) {
        if (copied) {
          toast('已复制 Token\n' + mask(result.token) + '\n来源 ' + result.from + '\n发给 QQ：/l u <Token>', true);
        } else {
          // 复制失败 → 弹出手动复制
          toast('自动复制失败，请长按下面内容手动复制：\n' + result.token, false);
          window.prompt('长按全选并复制 Token', result.token);
        }
      });
    });

    document.body.appendChild(btn);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', buildButton);
  } else {
    buildButton();
  }
})();
