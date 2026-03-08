/**
 * Argus LDD · Cliente Supabase (portal y seguimiento)
 * Carga Supabase desde CDN y expone crearDenuncia() y getSeguimiento().
 * Si no hay config (supabase-env.js), usa comportamiento mock/local.
 */
(function () {
  'use strict';

  var config = window.ArgusSupabase || {};
  var supabase = null;

  function getClient() {
    if (supabase) return supabase;
    if (!config.url || !config.anonKey) return null;
    var supabaseLib = window.supabase;
    if (!supabaseLib || typeof supabaseLib.createClient !== 'function') return null;
    supabase = supabaseLib.createClient(config.url, config.anonKey);
    return supabase;
  }

  /**
   * Crear una denuncia. Devuelve Promise<{ ok, tracking_code?, error? }>
   */
  function crearDenuncia(payload) {
    var client = getClient();
    if (!client) {
      return Promise.resolve({
        ok: false,
        error: 'Backend no configurado',
        _mock: true
      });
    }
    return client.rpc('crear_denuncia', {
      p_tenant_slug: payload.tenant_slug || 'default',
      p_category: payload.category || null,
      p_categories: payload.categories || null,
      p_description: payload.description || null,
      p_area: payload.area || null,
      p_anonymous: payload.anonymous !== false,
      p_contact_name: payload.contact_name || null,
      p_contact_email: payload.contact_email || null,
      p_contact_phone: payload.contact_phone || null,
      p_metadata: payload.metadata || {}
    }).then(function (res) {
      if (res.error) {
        return { ok: false, error: res.error.message || 'Error al crear denuncia' };
      }
      var data = res.data || {};
      if (data.ok) {
        return { ok: true, tracking_code: data.tracking_code, id: data.id };
      }
      return { ok: false, error: data.error || 'Error desconocido' };
    }).catch(function (err) {
      return { ok: false, error: err.message || 'Error de conexión' };
    });
  }

  /**
   * Consultar estado por código. Devuelve Promise<{ ok, found?, status?, label?, date?, msg? }>
   */
  function getSeguimiento(trackingCode) {
    var client = getClient();
    if (!client) {
      return Promise.resolve({
        ok: false,
        found: false,
        error: 'Backend no configurado',
        _mock: true
      });
    }
    return client.rpc('get_seguimiento', {
      p_tracking_code: (trackingCode || '').trim()
    }).then(function (res) {
      if (res.error) {
        return { ok: false, found: false, error: res.error.message };
      }
      var data = res.data || {};
      if (data.ok === false) {
        return {
          ok: false,
          found: data.found || false,
          error: data.error || 'Código no encontrado'
        };
      }
      return {
        ok: true,
        found: true,
        status: data.status,
        label: data.label,
        date: data.date,
        tracking_code: data.tracking_code,
        msg: data.msg || null
      };
    }).catch(function (err) {
      return { ok: false, found: false, error: err.message || 'Error de conexión' };
    });
  }

  /**
   * Back office: listar casos del tenant. Devuelve Promise<{ ok, casos[] }>
   */
  function listarCasosTenant(tenantSlug) {
    var client = getClient();
    if (!client) return Promise.resolve({ ok: false, casos: [] });
    return client.rpc('listar_casos_tenant', { p_tenant_slug: tenantSlug || 'default' })
      .then(function (res) {
        if (res.error) return { ok: false, casos: [] };
        var d = res.data || {};
        return { ok: d.ok === true, casos: d.casos || [], error: d.error };
      })
      .catch(function () { return { ok: false, casos: [] }; });
  }

  /**
   * Back office: detalle de un caso. Devuelve Promise<{ ok, caso? }>
   */
  function getCasoPorId(casoId, tenantSlug) {
    var client = getClient();
    if (!client) return Promise.resolve({ ok: false });
    return client.rpc('get_caso_por_id', { p_caso_id: casoId, p_tenant_slug: tenantSlug || 'default' })
      .then(function (res) {
        if (res.error) return { ok: false };
        var d = res.data || {};
        return { ok: d.ok === true, caso: d.caso, error: d.error };
      })
      .catch(function () { return { ok: false }; });
  }

  /**
   * Back office: mensajes de seguimiento (los que ve el denunciante al consultar por código).
   * Devuelve Promise<{ ok, mensajes[] }>
   */
  function getSeguimientoMensajes(casoId, tenantSlug) {
    var client = getClient();
    if (!client) return Promise.resolve({ ok: false, mensajes: [] });
    return client.rpc('get_seguimiento_mensajes', { p_caso_id: casoId, p_tenant_slug: tenantSlug || 'default' })
      .then(function (res) {
        if (res.error) return { ok: false, mensajes: [] };
        var d = res.data || {};
        return { ok: d.ok === true, mensajes: d.mensajes || [], error: d.error };
      })
      .catch(function () { return { ok: false, mensajes: [] }; });
  }

  /**
   * Back office: enviar mensaje al denunciante. El denunciante lo ve al consultar por código.
   * Devuelve Promise<{ ok, id?, error? }>
   */
  function enviarMensajeDenunciante(casoId, tenantSlug, title, message) {
    var client = getClient();
    if (!client) return Promise.resolve({ ok: false, error: 'Backend no configurado' });
    return client.rpc('enviar_mensaje_denunciante', {
      p_caso_id: casoId,
      p_tenant_slug: tenantSlug || 'default',
      p_title: title || null,
      p_message: (message || '').trim()
    }).then(function (res) {
      if (res.error) return { ok: false, error: res.error.message };
      var d = res.data || {};
      return { ok: d.ok === true, id: d.id, error: d.error };
    }).catch(function (err) { return { ok: false, error: err.message }; });
  }

  /**
   * Back office: actualizar estado del caso (pending | active | closed).
   */
  function actualizarEstadoCaso(casoId, tenantSlug, status) {
    var client = getClient();
    if (!client) return Promise.resolve({ ok: false });
    return client.rpc('actualizar_estado_caso', {
      p_caso_id: casoId,
      p_tenant_slug: tenantSlug || 'default',
      p_status: status
    }).then(function (res) {
      if (res.error) return { ok: false, error: res.error.message };
      var d = res.data || {};
      return { ok: d.ok === true, error: d.error };
    }).catch(function (err) { return { ok: false, error: err.message }; });
  }

  window.ArgusBackend = {
    isConfigured: function () {
      return !!(config.url && config.anonKey);
    },
    crearDenuncia: crearDenuncia,
    getSeguimiento: getSeguimiento,
    listarCasosTenant: listarCasosTenant,
    getCasoPorId: getCasoPorId,
    getSeguimientoMensajes: getSeguimientoMensajes,
    enviarMensajeDenunciante: enviarMensajeDenunciante,
    actualizarEstadoCaso: actualizarEstadoCaso
  };
})();
