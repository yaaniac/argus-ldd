-- ============================================================
-- Argus LDD · Migration 007: mensajes bidireccionales
-- El denunciante puede responder desde la página de seguimiento.
-- Ejecutar en SQL Editor después de 006_status_y_riskeval.sql
-- ============================================================

-- ── 1. Agregar campo sender a caso_seguimiento ────────────────
-- 'team'        = mensaje del equipo de compliance
-- 'denunciante' = mensaje enviado por el denunciante
ALTER TABLE public.caso_seguimiento
  ADD COLUMN IF NOT EXISTS sender TEXT NOT NULL DEFAULT 'team';

-- ── 2. RPC: denunciante envía un mensaje (autenticado por tracking_code) ─
CREATE OR REPLACE FUNCTION public.enviar_mensaje_seguimiento(
  p_tracking_code TEXT,
  p_message       TEXT,
  p_title         TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_caso      RECORD;
  v_msg_id    UUID;
BEGIN
  IF NULLIF(trim(COALESCE(p_message, '')), '') IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'El mensaje no puede estar vacío');
  END IF;

  IF NULLIF(trim(COALESCE(p_tracking_code, '')), '') IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Código de seguimiento requerido');
  END IF;

  SELECT id, tenant_id INTO v_caso
  FROM public.casos
  WHERE tracking_code = upper(trim(p_tracking_code))
  LIMIT 1;

  IF v_caso.id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Código no encontrado');
  END IF;

  INSERT INTO public.caso_seguimiento (caso_id, title, message, sender)
  VALUES (v_caso.id,
          NULLIF(trim(COALESCE(p_title, '')), ''),
          trim(p_message),
          'denunciante')
  RETURNING id INTO v_msg_id;

  -- Registrar en el log de auditoría del caso
  INSERT INTO public.caso_log (caso_id, tenant_id, action, author, color)
  VALUES (v_caso.id, v_caso.tenant_id, 'Denunciante envió un mensaje', 'Denunciante', 'primary');

  RETURN jsonb_build_object('ok', true, 'id', v_msg_id);
END;
$$;

-- ── 3. get_seguimiento: incluir sender en mensajes ────────────
-- (Reemplaza la versión de 005_seguimiento_mensajes.sql)
CREATE OR REPLACE FUNCTION public.get_seguimiento(p_tracking_code TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_caso     RECORD;
  v_mensajes JSONB;
BEGIN
  SELECT c.id, c.status, c.created_at, c.tracking_code
  INTO v_caso
  FROM public.casos c
  WHERE c.tracking_code = upper(trim(p_tracking_code))
  LIMIT 1;

  IF v_caso.id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'found', false, 'error', 'Código no encontrado');
  END IF;

  SELECT COALESCE(jsonb_agg(
    jsonb_build_object(
      'id',         s.id,
      'title',      s.title,
      'message',    s.message,
      'sender',     s.sender,
      'created_at', s.created_at
    ) ORDER BY s.created_at ASC
  ), '[]'::jsonb) INTO v_mensajes
  FROM public.caso_seguimiento s
  WHERE s.caso_id = v_caso.id;

  RETURN jsonb_build_object(
    'ok',           true,
    'found',        true,
    'tracking_code',v_caso.tracking_code,
    'status',       v_caso.status,
    'label', CASE v_caso.status
      WHEN 'new'           THEN 'Recibida'
      WHEN 'pending'       THEN 'En evaluación'
      WHEN 'eval'          THEN 'En evaluación'
      WHEN 'investigating' THEN 'En investigación'
      WHEN 'active'        THEN 'En investigación'
      WHEN 'review'        THEN 'En revisión'
      WHEN 'closed'        THEN 'Cerrada'
      ELSE 'En proceso' END,
    'date',         to_char(v_caso.created_at AT TIME ZONE 'America/Argentina/Buenos_Aires',
                            'DD/MM/YYYY'),
    'mensajes',     v_mensajes
  );
END;
$$;

-- ── 4. get_caso_detalle_completo: incluir sender en mensajes ──
-- (Solo actualiza el SELECT de mensajes para incluir sender)
CREATE OR REPLACE FUNCTION public.get_caso_detalle_completo(
  p_caso_id     UUID,
  p_tenant_slug TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_tenant_id UUID;
  v_caso      RECORD;
  v_tareas    JSONB;
  v_hallazgos JSONB;
  v_log       JSONB;
  v_mensajes  JSONB;
BEGIN
  SELECT id INTO v_tenant_id FROM public.tenants WHERE slug = p_tenant_slug LIMIT 1;
  IF v_tenant_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Tenant no encontrado');
  END IF;

  SELECT c.id, c.tracking_code, c.status, c.category, c.categories,
         c.description, c.area, c.anonymous, c.contact_name, c.contact_email, c.contact_phone,
         c.metadata, c.assigned_to, c.risk_level, c.risk_eval, c.created_at, c.updated_at
  INTO v_caso
  FROM public.casos c
  WHERE c.id = p_caso_id AND c.tenant_id = v_tenant_id
  LIMIT 1;

  IF v_caso.id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Caso no encontrado');
  END IF;

  -- Tareas
  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'id', t.id, 'title', t.title, 'description', t.description,
    'assigned_to', t.assigned_to, 'status', t.status,
    'due_date', t.due_date, 'created_at', t.created_at, 'updated_at', t.updated_at
  ) ORDER BY t.created_at ASC), '[]'::jsonb) INTO v_tareas
  FROM public.caso_tareas t WHERE t.caso_id = p_caso_id;

  -- Hallazgos
  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'id', h.id, 'content', h.content, 'relevance', h.relevance,
    'author', h.author, 'created_at', h.created_at
  ) ORDER BY h.created_at DESC), '[]'::jsonb) INTO v_hallazgos
  FROM public.caso_hallazgos h WHERE h.caso_id = p_caso_id;

  -- Log
  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'id', l.id, 'action', l.action, 'author', l.author,
    'detail', l.detail, 'color', l.color, 'created_at', l.created_at
  ) ORDER BY l.created_at DESC), '[]'::jsonb) INTO v_log
  FROM public.caso_log l WHERE l.caso_id = p_caso_id;

  -- Mensajes (bidireccionales: incluye sender)
  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'id',         s.id,
    'title',      s.title,
    'message',    s.message,
    'sender',     s.sender,
    'created_at', s.created_at
  ) ORDER BY s.created_at ASC), '[]'::jsonb) INTO v_mensajes
  FROM public.caso_seguimiento s WHERE s.caso_id = p_caso_id;

  IF jsonb_array_length(v_log) = 0 THEN
    INSERT INTO public.caso_log (caso_id, tenant_id, action, author, color)
    VALUES (p_caso_id, v_tenant_id,
            'Caso recibido · Canal Web · Código: ' || v_caso.tracking_code,
            'Sistema', 'primary');
    SELECT COALESCE(jsonb_agg(jsonb_build_object(
      'id', l.id, 'action', l.action, 'author', l.author,
      'detail', l.detail, 'color', l.color, 'created_at', l.created_at
    ) ORDER BY l.created_at DESC), '[]'::jsonb) INTO v_log
    FROM public.caso_log l WHERE l.caso_id = p_caso_id;
  END IF;

  RETURN jsonb_build_object(
    'ok', true,
    'caso', jsonb_build_object(
      'id',            v_caso.id,
      'tracking_code', v_caso.tracking_code,
      'status',        v_caso.status,
      'category',      v_caso.category,
      'categories',    v_caso.categories,
      'description',   v_caso.description,
      'area',          v_caso.area,
      'anonymous',     v_caso.anonymous,
      'contact_name',  v_caso.contact_name,
      'contact_email', v_caso.contact_email,
      'contact_phone', v_caso.contact_phone,
      'assigned_to',   v_caso.assigned_to,
      'risk_level',    v_caso.risk_level,
      'risk_eval',     v_caso.risk_eval,
      'created_at',    v_caso.created_at,
      'updated_at',    v_caso.updated_at
    ),
    'tareas',    v_tareas,
    'hallazgos', v_hallazgos,
    'log',       v_log,
    'mensajes',  v_mensajes
  );
END;
$$;

-- ── 5. get_seguimiento_mensajes: incluir sender ───────────────
CREATE OR REPLACE FUNCTION public.get_seguimiento_mensajes(p_caso_id UUID, p_tenant_slug TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_tenant_id UUID;
  v_caso_id   UUID;
  v_rows      JSONB;
BEGIN
  SELECT id INTO v_tenant_id FROM public.tenants WHERE slug = p_tenant_slug LIMIT 1;
  IF v_tenant_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'mensajes', '[]'::jsonb);
  END IF;

  SELECT c.id INTO v_caso_id FROM public.casos c
  WHERE c.id = p_caso_id AND c.tenant_id = v_tenant_id LIMIT 1;

  IF v_caso_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'mensajes', '[]'::jsonb);
  END IF;

  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'id', s.id, 'title', s.title, 'message', s.message,
    'sender', s.sender, 'created_at', s.created_at
  ) ORDER BY s.created_at ASC), '[]'::jsonb) INTO v_rows
  FROM public.caso_seguimiento s WHERE s.caso_id = v_caso_id;

  RETURN jsonb_build_object('ok', true, 'mensajes', v_rows);
END;
$$;

-- ── Permisos ──────────────────────────────────────────────────
GRANT EXECUTE ON FUNCTION public.enviar_mensaje_seguimiento(TEXT, TEXT, TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.enviar_mensaje_seguimiento(TEXT, TEXT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_seguimiento(TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.get_seguimiento(TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_caso_detalle_completo(UUID, TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.get_caso_detalle_completo(UUID, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_seguimiento_mensajes(UUID, TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.get_seguimiento_mensajes(UUID, TEXT) TO authenticated;
