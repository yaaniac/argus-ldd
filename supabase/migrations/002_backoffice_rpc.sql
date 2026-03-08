-- ============================================================
-- Argus LDD · Back office: listar casos, detalle, mensajes al denunciante
-- Ejecutar en SQL Editor después de 001_initial.sql
-- ============================================================

-- ── Listar casos del tenant (para el back office) ─────────────
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
      'id', c.id,
      'tracking_code', c.tracking_code,
      'status', c.status,
      'category', c.category,
      'area', c.area,
      'anonymous', COALESCE(c.anonymous, true),
      'created_at', c.created_at,
      'updated_at', c.updated_at,
      'description', LEFT(c.description, 200)
    ) ORDER BY c.created_at DESC
  ), '[]'::jsonb) INTO v_rows
  FROM public.casos c
  WHERE c.tenant_id = v_tenant_id;

  RETURN jsonb_build_object('ok', true, 'casos', v_rows);
END;
$$;

-- ── Detalle de un caso (solo si pertenece al tenant) ──────────
CREATE OR REPLACE FUNCTION public.get_caso_por_id(p_caso_id UUID, p_tenant_slug TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_tenant_id UUID;
  v_caso      RECORD;
BEGIN
  SELECT id INTO v_tenant_id FROM public.tenants WHERE slug = p_tenant_slug LIMIT 1;
  IF v_tenant_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Tenant no encontrado');
  END IF;

  SELECT c.id, c.tenant_id, c.tracking_code, c.status, c.category, c.categories,
         c.description, c.area, c.anonymous, c.contact_name, c.contact_email, c.contact_phone,
         c.metadata, c.created_at, c.updated_at
  INTO v_caso
  FROM public.casos c
  WHERE c.id = p_caso_id AND c.tenant_id = v_tenant_id
  LIMIT 1;

  IF v_caso.id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Caso no encontrado o no pertenece al tenant');
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
      'metadata', COALESCE(v_caso.metadata, '{}'),
      'created_at', v_caso.created_at,
      'updated_at', v_caso.updated_at
    )
  );
END;
$$;

-- ── Mensajes de seguimiento (lo que ve el denunciante al consultar por código) ──
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

  SELECT c.id INTO v_caso_id
  FROM public.casos c
  WHERE c.id = p_caso_id AND c.tenant_id = v_tenant_id
  LIMIT 1;

  IF v_caso_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'mensajes', '[]'::jsonb);
  END IF;

  SELECT COALESCE(jsonb_agg(
    jsonb_build_object(
      'id', s.id,
      'title', s.title,
      'message', s.message,
      'created_at', s.created_at
    ) ORDER BY s.created_at ASC
  ), '[]'::jsonb) INTO v_rows
  FROM public.caso_seguimiento s
  WHERE s.caso_id = v_caso_id;

  RETURN jsonb_build_object('ok', true, 'mensajes', v_rows);
END;
$$;

-- ── Enviar mensaje al denunciante (aparece cuando consulta por código) ──
CREATE OR REPLACE FUNCTION public.enviar_mensaje_denunciante(
  p_caso_id     UUID,
  p_tenant_slug TEXT,
  p_title       TEXT DEFAULT NULL,
  p_message     TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_tenant_id UUID;
  v_caso_id   UUID;
  v_msg_id    UUID;
BEGIN
  IF NULLIF(trim(COALESCE(p_message, '')), '') IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'El mensaje no puede estar vacío');
  END IF;

  SELECT id INTO v_tenant_id FROM public.tenants WHERE slug = p_tenant_slug LIMIT 1;
  IF v_tenant_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Tenant no encontrado');
  END IF;

  SELECT c.id INTO v_caso_id
  FROM public.casos c
  WHERE c.id = p_caso_id AND c.tenant_id = v_tenant_id
  LIMIT 1;

  IF v_caso_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Caso no encontrado');
  END IF;

  INSERT INTO public.caso_seguimiento (caso_id, title, message)
  VALUES (v_caso_id, NULLIF(trim(COALESCE(p_title, '')), ''), trim(p_message))
  RETURNING id INTO v_msg_id;

  RETURN jsonb_build_object('ok', true, 'id', v_msg_id);
END;
$$;

-- ── Actualizar estado del caso (desde back office) ─────────────
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
  v_tenant_id UUID;
  v_caso_id   UUID;
BEGIN
  IF p_status IS NULL OR p_status NOT IN ('pending', 'active', 'closed') THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Estado inválido');
  END IF;

  SELECT id INTO v_tenant_id FROM public.tenants WHERE slug = p_tenant_slug LIMIT 1;
  IF v_tenant_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Tenant no encontrado');
  END IF;

  UPDATE public.casos
  SET status = p_status, updated_at = now()
  WHERE id = p_caso_id AND tenant_id = v_tenant_id
  RETURNING id INTO v_caso_id;

  IF v_caso_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Caso no encontrado');
  END IF;

  RETURN jsonb_build_object('ok', true);
END;
$$;

GRANT EXECUTE ON FUNCTION public.listar_casos_tenant(TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.listar_casos_tenant(TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_caso_por_id(UUID, TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.get_caso_por_id(UUID, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_seguimiento_mensajes(UUID, TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.get_seguimiento_mensajes(UUID, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.enviar_mensaje_denunciante(UUID, TEXT, TEXT, TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.enviar_mensaje_denunciante(UUID, TEXT, TEXT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.actualizar_estado_caso(UUID, TEXT, TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.actualizar_estado_caso(UUID, TEXT, TEXT) TO authenticated;
