-- ============================================================
-- Argus LDD · Migration 006: estados granulares + risk_eval
-- Ejecutar en SQL Editor después de 005_seguimiento_mensajes.sql
-- ============================================================

-- ── 1. Limpiar DEFAULT de risk_level ─────────────────────────
-- Todos los 'medium' que existen se pusieron automáticamente por el
-- DEFAULT de la migración 003. Ningún usuario los asignó manualmente
-- todavía (el modal de evaluación existía solo en localStorage).
-- Los reseteamos a NULL para que los casos sin evaluación aparezcan
-- sin badge de riesgo en el dashboard.
UPDATE public.casos SET risk_level = NULL WHERE risk_level = 'medium';
ALTER TABLE public.casos ALTER COLUMN risk_level DROP DEFAULT;

-- ── 2. Agregar columna risk_eval (JSON de la evaluación completa) ─
ALTER TABLE public.casos ADD COLUMN IF NOT EXISTS risk_eval JSONB;

-- ── 3. listar_casos_tenant: sin COALESCE en risk_level ────────
-- Antes: COALESCE(c.risk_level, 'medium')  →  ahora: c.risk_level  (puede ser NULL)
CREATE OR REPLACE FUNCTION public.listar_casos_tenant(p_tenant_slug TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_tenant_id UUID;
  v_rows      JSONB;
BEGIN
  SELECT id INTO v_tenant_id FROM public.tenants WHERE slug = p_tenant_slug LIMIT 1;
  IF v_tenant_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Tenant no encontrado', 'casos', '[]'::jsonb);
  END IF;

  SELECT COALESCE(jsonb_agg(
    jsonb_build_object(
      'id',           c.id,
      'tracking_code',c.tracking_code,
      'status',       c.status,
      'category',     c.category,
      'categories',   to_jsonb(COALESCE(c.categories, ARRAY[]::text[])),
      'area',         c.area,
      'anonymous',    COALESCE(c.anonymous, true),
      'risk_level',   c.risk_level,
      'assigned_to',  c.assigned_to,
      'created_at',   c.created_at,
      'updated_at',   c.updated_at,
      'description',  LEFT(c.description, 200)
    ) ORDER BY c.created_at DESC
  ), '[]'::jsonb) INTO v_rows
  FROM public.casos c
  WHERE c.tenant_id = v_tenant_id;

  RETURN jsonb_build_object('ok', true, 'casos', v_rows);
END;
$$;

-- ── 4. get_caso_detalle_completo: incluir risk_eval ───────────
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

  -- Log de auditoría
  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'id', l.id, 'action', l.action, 'author', l.author,
    'detail', l.detail, 'color', l.color, 'created_at', l.created_at
  ) ORDER BY l.created_at DESC), '[]'::jsonb) INTO v_log
  FROM public.caso_log l WHERE l.caso_id = p_caso_id;

  -- Mensajes de seguimiento
  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'id', s.id, 'title', s.title, 'message', s.message, 'created_at', s.created_at
  ) ORDER BY s.created_at ASC), '[]'::jsonb) INTO v_mensajes
  FROM public.caso_seguimiento s WHERE s.caso_id = p_caso_id;

  -- Si el log está vacío, insertar entrada inicial automáticamente
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

-- ── 5. actualizar_estado_caso: aceptar estados granulares ─────
CREATE OR REPLACE FUNCTION public.actualizar_estado_caso(
  p_caso_id     UUID,
  p_tenant_slug TEXT,
  p_status      TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_tenant_id  UUID;
  v_caso       RECORD;
  v_label_old  TEXT;
  v_label_new  TEXT;
BEGIN
  -- Acepta tanto los valores UI granulares como los valores legacy
  IF p_status IS NULL OR p_status NOT IN (
    'new', 'pending', 'eval', 'investigating', 'active', 'review', 'closed'
  ) THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Estado inválido');
  END IF;

  SELECT id INTO v_tenant_id FROM public.tenants WHERE slug = p_tenant_slug LIMIT 1;
  IF v_tenant_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Tenant no encontrado');
  END IF;

  SELECT id, status INTO v_caso
  FROM public.casos
  WHERE id = p_caso_id AND tenant_id = v_tenant_id LIMIT 1;

  IF v_caso.id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Caso no encontrado');
  END IF;

  UPDATE public.casos
  SET status = p_status, updated_at = now()
  WHERE id = p_caso_id AND tenant_id = v_tenant_id;

  IF v_caso.status IS DISTINCT FROM p_status THEN
    v_label_old := CASE v_caso.status
      WHEN 'new'           THEN 'Nuevo'
      WHEN 'pending'       THEN 'Pendiente'
      WHEN 'eval'          THEN 'En evaluación'
      WHEN 'investigating' THEN 'En investigación'
      WHEN 'active'        THEN 'En investigación'
      WHEN 'review'        THEN 'En revisión'
      WHEN 'closed'        THEN 'Cerrado'
      ELSE v_caso.status END;
    v_label_new := CASE p_status
      WHEN 'new'           THEN 'Nuevo'
      WHEN 'pending'       THEN 'Pendiente'
      WHEN 'eval'          THEN 'En evaluación'
      WHEN 'investigating' THEN 'En investigación'
      WHEN 'active'        THEN 'En investigación'
      WHEN 'review'        THEN 'En revisión'
      WHEN 'closed'        THEN 'Cerrado'
      ELSE p_status END;

    INSERT INTO public.caso_log (caso_id, tenant_id, action, author, color)
    VALUES (p_caso_id, v_tenant_id,
            'Estado cambiado: ' || v_label_old || ' → ' || v_label_new,
            'Sistema', 'primary');
  END IF;

  RETURN jsonb_build_object('ok', true);
END;
$$;

-- ── 6. Nueva RPC: guardar evaluación de riesgo ────────────────
CREATE OR REPLACE FUNCTION public.actualizar_risk_eval(
  p_caso_id     UUID,
  p_tenant_slug TEXT,
  p_risk_eval   JSONB,
  p_risk_level  TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_tenant_id UUID;
  v_caso_id   UUID;
BEGIN
  SELECT id INTO v_tenant_id FROM public.tenants WHERE slug = p_tenant_slug LIMIT 1;
  IF v_tenant_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Tenant no encontrado');
  END IF;

  UPDATE public.casos
  SET risk_eval  = p_risk_eval,
      risk_level = CASE WHEN p_risk_level IS NOT NULL THEN p_risk_level ELSE risk_level END,
      updated_at = now()
  WHERE id = p_caso_id AND tenant_id = v_tenant_id
  RETURNING id INTO v_caso_id;

  IF v_caso_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Caso no encontrado');
  END IF;

  INSERT INTO public.caso_log (caso_id, tenant_id, action, author, color)
  VALUES (p_caso_id, v_tenant_id, 'Evaluación de riesgo actualizada', 'Sistema', 'purple');

  RETURN jsonb_build_object('ok', true);
END;
$$;

-- ── Permisos ──────────────────────────────────────────────────
GRANT EXECUTE ON FUNCTION public.listar_casos_tenant(TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.listar_casos_tenant(TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_caso_detalle_completo(UUID, TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.get_caso_detalle_completo(UUID, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.actualizar_estado_caso(UUID, TEXT, TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.actualizar_estado_caso(UUID, TEXT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.actualizar_risk_eval(UUID, TEXT, JSONB, TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.actualizar_risk_eval(UUID, TEXT, JSONB, TEXT) TO authenticated;
