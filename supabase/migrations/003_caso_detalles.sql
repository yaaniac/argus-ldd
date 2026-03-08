-- ============================================================
-- Argus LDD · Detalle de caso: tareas, hallazgos, log de auditoría
-- Ejecutar en SQL Editor después de 002_backoffice_rpc.sql
-- ============================================================

-- ── Agregar campos a casos ────────────────────────────────────
ALTER TABLE public.casos
  ADD COLUMN IF NOT EXISTS assigned_to TEXT,
  ADD COLUMN IF NOT EXISTS risk_level  TEXT DEFAULT 'medium';

-- ── Tabla: tareas del caso ────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.caso_tareas (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  caso_id     UUID NOT NULL REFERENCES public.casos(id) ON DELETE CASCADE,
  tenant_id   UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  title       TEXT NOT NULL,
  description TEXT,
  assigned_to TEXT,
  status      TEXT NOT NULL DEFAULT 'pending',
  due_date    DATE,
  created_at  TIMESTAMPTZ DEFAULT now(),
  updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tareas_caso ON public.caso_tareas(caso_id);

ALTER TABLE public.caso_tareas ENABLE ROW LEVEL SECURITY;
CREATE POLICY "caso_tareas_no_anon" ON public.caso_tareas FOR ALL USING (false);

-- ── Tabla: hallazgos del caso ─────────────────────────────────
CREATE TABLE IF NOT EXISTS public.caso_hallazgos (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  caso_id     UUID NOT NULL REFERENCES public.casos(id) ON DELETE CASCADE,
  tenant_id   UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  content     TEXT NOT NULL,
  relevance   TEXT DEFAULT 'medium',
  author      TEXT,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hallazgos_caso ON public.caso_hallazgos(caso_id);

ALTER TABLE public.caso_hallazgos ENABLE ROW LEVEL SECURITY;
CREATE POLICY "caso_hallazgos_no_anon" ON public.caso_hallazgos FOR ALL USING (false);

-- ── Tabla: log de auditoría ───────────────────────────────────
CREATE TABLE IF NOT EXISTS public.caso_log (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  caso_id     UUID NOT NULL REFERENCES public.casos(id) ON DELETE CASCADE,
  tenant_id   UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  action      TEXT NOT NULL,
  author      TEXT DEFAULT 'Sistema',
  detail      TEXT,
  color       TEXT DEFAULT 'primary',
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_log_caso ON public.caso_log(caso_id, created_at DESC);

ALTER TABLE public.caso_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "caso_log_no_anon" ON public.caso_log FOR ALL USING (false);

-- ── RPC: detalle completo del caso (un solo llamado) ──────────
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
         c.metadata, c.assigned_to, c.risk_level, c.created_at, c.updated_at
  INTO v_caso
  FROM public.casos c
  WHERE c.id = p_caso_id AND c.tenant_id = v_tenant_id
  LIMIT 1;

  IF v_caso.id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Caso no encontrado');
  END IF;

  -- Tareas
  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'id', t.id,
    'title', t.title,
    'description', t.description,
    'assigned_to', t.assigned_to,
    'status', t.status,
    'due_date', t.due_date,
    'created_at', t.created_at,
    'updated_at', t.updated_at
  ) ORDER BY t.created_at ASC), '[]'::jsonb) INTO v_tareas
  FROM public.caso_tareas t WHERE t.caso_id = p_caso_id;

  -- Hallazgos
  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'id', h.id,
    'content', h.content,
    'relevance', h.relevance,
    'author', h.author,
    'created_at', h.created_at
  ) ORDER BY h.created_at DESC), '[]'::jsonb) INTO v_hallazgos
  FROM public.caso_hallazgos h WHERE h.caso_id = p_caso_id;

  -- Log de auditoría
  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'id', l.id,
    'action', l.action,
    'author', l.author,
    'detail', l.detail,
    'color', l.color,
    'created_at', l.created_at
  ) ORDER BY l.created_at DESC), '[]'::jsonb) INTO v_log
  FROM public.caso_log l WHERE l.caso_id = p_caso_id;

  -- Mensajes de seguimiento
  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'id', s.id,
    'title', s.title,
    'message', s.message,
    'created_at', s.created_at
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
      'id', v_caso.id,
      'tracking_code', v_caso.tracking_code,
      'status', v_caso.status,
      'category', v_caso.category,
      'categories', v_caso.categories,
      'description', v_caso.description,
      'area', v_caso.area,
      'anonymous', v_caso.anonymous,
      'contact_name', v_caso.contact_name,
      'contact_email', v_caso.contact_email,
      'contact_phone', v_caso.contact_phone,
      'assigned_to', v_caso.assigned_to,
      'risk_level', v_caso.risk_level,
      'created_at', v_caso.created_at,
      'updated_at', v_caso.updated_at
    ),
    'tareas', v_tareas,
    'hallazgos', v_hallazgos,
    'log', v_log,
    'mensajes', v_mensajes
  );
END;
$$;

-- ── RPC: asignar investigador ─────────────────────────────────
CREATE OR REPLACE FUNCTION public.asignar_investigador(
  p_caso_id     UUID,
  p_tenant_slug TEXT,
  p_investigator TEXT
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
  SET assigned_to = NULLIF(trim(COALESCE(p_investigator, '')), ''), updated_at = now()
  WHERE id = p_caso_id AND tenant_id = v_tenant_id
  RETURNING id INTO v_caso_id;

  IF v_caso_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Caso no encontrado');
  END IF;

  INSERT INTO public.caso_log (caso_id, tenant_id, action, author, color)
  VALUES (p_caso_id, v_tenant_id,
          'Investigador asignado: ' || COALESCE(NULLIF(trim(p_investigator), ''), '—'),
          'Sistema', 'primary');

  RETURN jsonb_build_object('ok', true);
END;
$$;

-- ── RPC: crear tarea ──────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.crear_tarea(
  p_caso_id     UUID,
  p_tenant_slug TEXT,
  p_title       TEXT,
  p_description TEXT DEFAULT NULL,
  p_assigned_to TEXT DEFAULT NULL,
  p_due_date    DATE DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_tenant_id UUID;
  v_caso_id   UUID;
  v_tarea_id  UUID;
BEGIN
  IF NULLIF(trim(COALESCE(p_title, '')), '') IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'El título es requerido');
  END IF;

  SELECT id INTO v_tenant_id FROM public.tenants WHERE slug = p_tenant_slug LIMIT 1;
  IF v_tenant_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Tenant no encontrado');
  END IF;

  SELECT c.id INTO v_caso_id FROM public.casos c
  WHERE c.id = p_caso_id AND c.tenant_id = v_tenant_id LIMIT 1;
  IF v_caso_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Caso no encontrado');
  END IF;

  INSERT INTO public.caso_tareas (caso_id, tenant_id, title, description, assigned_to, due_date)
  VALUES (p_caso_id, v_tenant_id, trim(p_title),
          NULLIF(trim(COALESCE(p_description, '')), ''),
          NULLIF(trim(COALESCE(p_assigned_to, '')), ''),
          p_due_date)
  RETURNING id INTO v_tarea_id;

  INSERT INTO public.caso_log (caso_id, tenant_id, action, author, color)
  VALUES (p_caso_id, v_tenant_id,
          'Tarea creada: ' || trim(p_title),
          COALESCE(NULLIF(trim(COALESCE(p_assigned_to, '')), ''), 'Sistema'), 'primary');

  RETURN jsonb_build_object('ok', true, 'id', v_tarea_id);
END;
$$;

-- ── RPC: actualizar estado de tarea ──────────────────────────
CREATE OR REPLACE FUNCTION public.actualizar_tarea(
  p_tarea_id    UUID,
  p_tenant_slug TEXT,
  p_status      TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_tenant_id UUID;
  v_tarea     RECORD;
BEGIN
  SELECT id INTO v_tenant_id FROM public.tenants WHERE slug = p_tenant_slug LIMIT 1;
  IF v_tenant_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Tenant no encontrado');
  END IF;

  SELECT t.id, t.caso_id, t.title INTO v_tarea
  FROM public.caso_tareas t
  WHERE t.id = p_tarea_id AND t.tenant_id = v_tenant_id LIMIT 1;

  IF v_tarea.id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Tarea no encontrada');
  END IF;

  UPDATE public.caso_tareas SET status = p_status, updated_at = now()
  WHERE id = p_tarea_id;

  INSERT INTO public.caso_log (caso_id, tenant_id, action, author, color)
  VALUES (v_tarea.caso_id, v_tenant_id,
          CASE WHEN p_status = 'done' THEN 'Tarea completada: ' ELSE 'Tarea reabierta: ' END || v_tarea.title,
          'Sistema',
          CASE WHEN p_status = 'done' THEN 'green' ELSE 'primary' END);

  RETURN jsonb_build_object('ok', true);
END;
$$;

-- ── RPC: registrar hallazgo ───────────────────────────────────
CREATE OR REPLACE FUNCTION public.crear_hallazgo(
  p_caso_id     UUID,
  p_tenant_slug TEXT,
  p_content     TEXT,
  p_relevance   TEXT DEFAULT 'medium',
  p_author      TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_tenant_id   UUID;
  v_caso_id     UUID;
  v_hallazgo_id UUID;
BEGIN
  IF NULLIF(trim(COALESCE(p_content, '')), '') IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'El contenido es requerido');
  END IF;

  SELECT id INTO v_tenant_id FROM public.tenants WHERE slug = p_tenant_slug LIMIT 1;
  IF v_tenant_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Tenant no encontrado');
  END IF;

  SELECT c.id INTO v_caso_id FROM public.casos c
  WHERE c.id = p_caso_id AND c.tenant_id = v_tenant_id LIMIT 1;
  IF v_caso_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Caso no encontrado');
  END IF;

  INSERT INTO public.caso_hallazgos (caso_id, tenant_id, content, relevance, author)
  VALUES (p_caso_id, v_tenant_id, trim(p_content),
          COALESCE(NULLIF(trim(COALESCE(p_relevance, '')), ''), 'medium'),
          NULLIF(trim(COALESCE(p_author, '')), ''))
  RETURNING id INTO v_hallazgo_id;

  INSERT INTO public.caso_log (caso_id, tenant_id, action, author, color)
  VALUES (p_caso_id, v_tenant_id,
          'Hallazgo registrado',
          COALESCE(NULLIF(trim(COALESCE(p_author, '')), ''), 'Sistema'), 'purple');

  RETURN jsonb_build_object('ok', true, 'id', v_hallazgo_id);
END;
$$;

-- ── RPC: actualizar_estado_caso (reemplaza 002, ahora loggea) ─
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
  IF p_status IS NULL OR p_status NOT IN ('pending', 'active', 'closed') THEN
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
      WHEN 'pending' THEN 'Pendiente' WHEN 'active' THEN 'En investigación'
      WHEN 'closed'  THEN 'Cerrado'   ELSE v_caso.status END;
    v_label_new := CASE p_status
      WHEN 'pending' THEN 'Pendiente' WHEN 'active' THEN 'En investigación'
      WHEN 'closed'  THEN 'Cerrado'   ELSE p_status END;

    INSERT INTO public.caso_log (caso_id, tenant_id, action, author, color)
    VALUES (p_caso_id, v_tenant_id,
            'Estado cambiado: ' || v_label_old || ' → ' || v_label_new,
            'Sistema', 'primary');
  END IF;

  RETURN jsonb_build_object('ok', true);
END;
$$;

-- ── Permisos ──────────────────────────────────────────────────
GRANT EXECUTE ON FUNCTION public.get_caso_detalle_completo(UUID, TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.get_caso_detalle_completo(UUID, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.asignar_investigador(UUID, TEXT, TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.asignar_investigador(UUID, TEXT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.crear_tarea(UUID, TEXT, TEXT, TEXT, TEXT, DATE) TO anon;
GRANT EXECUTE ON FUNCTION public.crear_tarea(UUID, TEXT, TEXT, TEXT, TEXT, DATE) TO authenticated;
GRANT EXECUTE ON FUNCTION public.actualizar_tarea(UUID, TEXT, TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.actualizar_tarea(UUID, TEXT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.crear_hallazgo(UUID, TEXT, TEXT, TEXT, TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.crear_hallazgo(UUID, TEXT, TEXT, TEXT, TEXT) TO authenticated;
