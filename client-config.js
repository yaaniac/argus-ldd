/**
 * client-config.js
 * Config centralizada del cliente. Se guarda en localStorage.
 * Cada página pública la incluye y llama a ArgusConfig.apply().
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'argus_client_config';

  var DEFAULTS = {
    empresa: {
      nombre:    'Argus',
      slogan:    'Línea de denuncias confidencial',
      logoUrl:   '',
      email:     'denuncias@empresa.com',
      telefono:  '0800-ARGUS',
      website:   'https://argus.com.ar'
    },
    landing: {
      heroTitle:    'Tu denuncia importa.<br/>Tu identidad, protegida.',
      heroSubtitle: 'Canal seguro, anónimo y confidencial para reportar irregularidades. Tecnología de cifrado end-to-end. Gestión profesional por compliance officers certificados.',
      ctaLabel:     'Hacer una denuncia',
      ctaSecLabel:  'Seguir mi caso'
    },
    categorias: [
      'Fraude / Malversación',
      'Acoso laboral',
      'Acoso sexual',
      'Corrupción / Soborno',
      'Conflicto de interés',
      'Discriminación',
      'Seguridad e higiene',
      'AML / Lavado de dinero',
      'Privacidad / datos',
      'Otro'
    ],
    canales: {
      web:       true,
      email:     true,
      telefono:  true,
      whatsapp:  true
    },
    faq: [
      {
        q: '¿Es realmente anónimo?',
        a: 'Sí. No registramos direcciones IP, dispositivos ni metadatos. Podés denunciar sin revelar tu identidad en ningún momento del proceso.'
      },
      {
        q: '¿Qué pasa después de que envío mi denuncia?',
        a: 'Recibís un código único. El equipo de compliance la evalúa en 72 horas hábiles y te informa el estado vía el mismo canal, sin revelar tu identidad.'
      },
      {
        q: '¿Quién tiene acceso a mi denuncia?',
        a: 'Solo el equipo de compliance certificado asignado a tu organización. Existe un protocolo estricto de confidencialidad y acceso por roles.'
      },
      {
        q: '¿Puedo hacer un seguimiento de mi caso?',
        a: 'Sí. Con el código que recibís podés consultar el estado de tu denuncia en cualquier momento, de forma completamente anónima.'
      },
      {
        q: '¿En qué países opera Argus?',
        a: 'Argentina, Uruguay, Chile, Brasil y España. Para otros países, consultanos: operamos bajo los estándares OCDE y GAFI aplicables en cada jurisdicción.'
      }
    ],
    formulario: {
      camposExtra: []   // {id, label, tipo: 'text'|'select'|'textarea', opciones: []}
    },
    apariencia: {
      colorPrimario: '#0097A7',
      colorSidebar:  '#003D44'
    }
  };

  /* ────────────────────────────────────────────────────────────
     API pública
  ──────────────────────────────────────────────────────────── */
  var ArgusConfig = {

    /** Devuelve la config completa (merge de defaults + guardado) */
    get: function () {
      try {
        var saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
        return deepMerge(DEFAULTS, saved);
      } catch (e) {
        return JSON.parse(JSON.stringify(DEFAULTS));
      }
    },

    /** Guarda (merge parcial) */
    save: function (partial) {
      var current = this.get();
      var merged  = deepMerge(current, partial);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
      return merged;
    },

    /** Reemplaza una sección completa (ej. categorias array) */
    set: function (key, value) {
      var current = this.get();
      current[key] = value;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
    },

    /** Restaura defaults */
    reset: function () {
      localStorage.removeItem(STORAGE_KEY);
    },

    /**
     * Aplica la config a la página actual.
     * Solo toca elementos marcados con data-cfg="..."
     */
    apply: function () {
      var cfg = this.get();

      /* Nombre de empresa */
      each('[data-cfg="empresa.nombre"]',    function (el) { el.textContent = cfg.empresa.nombre; });
      each('[data-cfg="empresa.slogan"]',    function (el) { el.textContent = cfg.empresa.slogan; });
      each('[data-cfg="empresa.email"]',     function (el) {
        el.textContent = cfg.empresa.email;
        if (el.tagName === 'A') el.href = 'mailto:' + cfg.empresa.email;
      });
      each('[data-cfg="empresa.telefono"]',  function (el) { el.textContent = cfg.empresa.telefono; });

      /* Hero */
      each('[data-cfg="landing.heroTitle"]',    function (el) { el.innerHTML  = cfg.landing.heroTitle; });
      each('[data-cfg="landing.heroSubtitle"]', function (el) { el.textContent = cfg.landing.heroSubtitle; });
      each('[data-cfg="landing.ctaLabel"]',     function (el) { el.textContent = cfg.landing.ctaLabel; });
      each('[data-cfg="landing.ctaSecLabel"]',  function (el) { el.textContent = cfg.landing.ctaSecLabel; });

      /* Logo */
      if (cfg.empresa.logoUrl) {
        each('[data-cfg="empresa.logo"]', function (el) {
          el.src = cfg.empresa.logoUrl;
          el.style.display = 'inline';
        });
      }

      /* Categorías en selects del formulario */
      each('[data-cfg="categorias-select"]', function (sel) {
        var first = sel.options[0];
        sel.innerHTML = '';
        if (first) sel.appendChild(first);
        cfg.categorias.forEach(function (cat) {
          var opt = document.createElement('option');
          opt.value = cat;
          opt.textContent = cat;
          sel.appendChild(opt);
        });
      });

      /* Canales: ocultar si está desactivado */
      ['web','email','telefono','whatsapp'].forEach(function (ch) {
        if (!cfg.canales[ch]) {
          each('[data-cfg-canal="' + ch + '"]', function (el) {
            el.style.display = 'none';
          });
        }
      });

      /* Color primario (CSS variable) */
      if (cfg.apariencia.colorPrimario) {
        document.documentElement.style.setProperty('--primary', cfg.apariencia.colorPrimario);
      }
      if (cfg.apariencia.colorSidebar) {
        document.documentElement.style.setProperty('--gray-900', cfg.apariencia.colorSidebar);
      }
    }
  };

  /* ── helpers ── */
  function each(sel, fn) {
    document.querySelectorAll(sel).forEach(fn);
  }

  function deepMerge(target, source) {
    var out = JSON.parse(JSON.stringify(target));
    if (!source || typeof source !== 'object') return out;
    Object.keys(source).forEach(function (k) {
      if (Array.isArray(source[k])) {
        out[k] = source[k];
      } else if (source[k] && typeof source[k] === 'object' && !Array.isArray(target[k])) {
        out[k] = deepMerge(target[k] || {}, source[k]);
      } else if (source[k] !== undefined) {
        out[k] = source[k];
      }
    });
    return out;
  }

  window.ArgusConfig = ArgusConfig;
})();
