-- ============================================================
-- Argus LDD · Migration 005: get_seguimiento devuelve todos los mensajes
-- Ejecutar en SQL Editor después de 004_dashboard.sql
-- ============================================================

-- Reemplaza la función para devolver TODOS los mensajes del equipo
-- (antes solo devolvía el último, con LIMIT 1)

CREATE OR REPLACE FUNCTION public.get_seguimiento(p_tracking_code TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_caso      RECORD;
  v_status    TEXT;
  v_label     TEXT;
  v_mensajes  JSONB;
BEGIN
  IF p_tracking_code IS NULL OR length(trim(p_tracking_code)) < 5 THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Código inválido');
  END IF;

  SELECT c.id, c.tracking_code, c.status, c.created_at, c.updated_at
  INTO v_caso
  FROM public.casos c
  WHERE upper(trim(c.tracking_code)) = upper(trim(p_tracking_code))
  LIMIT 1;

  IF v_caso.id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'found', false, 'error', 'Código no encontrado');
  END IF;

  v_status := COALESCE(v_caso.status, 'pending');
  v_label  := CASE v_status
    WHEN 'new'           THEN 'Pendiente de evaluación'
    WHEN 'pending'       THEN 'Pendiente de evaluación'
    WHEN 'investigating' THEN 'En investigación'
    WHEN 'active'        THEN 'En investigación'
    WHEN 'closed'        THEN 'Resuelto'
    ELSE 'Pendiente de evaluación'
  END;

  -- Todos los mensajes del equipo al denunciante, orden cronológico
  SELECT COALESCE(jsonb_agg(
    jsonb_build_object(
      'id',         s.id,
      'title',      s.title,
      'message',    s.message,
      'created_at', s.created_at
    ) ORDER BY s.created_at ASC
  ), '[]'::jsonb) INTO v_mensajes
  FROM public.caso_seguimiento s
  WHERE s.caso_id = v_caso.id;

  RETURN jsonb_build_object(
    'ok',           true,
    'found',        true,
    'tracking_code',v_caso.tracking_code,
    'status',       v_status,
    'label',        v_label,
    'date',         to_char(v_caso.updated_at, 'DD Mon YYYY — HH24:MI') || ' hs',
    'created_at',   v_caso.created_at,
    'mensajes',     v_mensajes
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_seguimiento(TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.get_seguimiento(TEXT) TO authenticated;
