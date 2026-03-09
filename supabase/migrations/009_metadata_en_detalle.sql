-- ── Migración 009: Incluir metadata en get_caso_detalle_completo ──────────────
-- El campo metadata (JSONB) ya existe en la tabla casos y en crear_denuncia,
-- pero no se devolvía en get_caso_detalle_completo.
-- Esta migración lo agrega para que el backoffice pueda mostrarlo.

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
      'metadata',      COALESCE(v_caso.metadata, '{}'::jsonb),
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
