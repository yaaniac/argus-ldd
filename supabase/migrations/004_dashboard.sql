-- ============================================================
-- Argus LDD · Migration 004: add risk_level to listar_casos_tenant
-- Ejecutar en SQL Editor después de 003_caso_detalles.sql
-- ============================================================

-- ── Actualizar listar_casos_tenant para incluir risk_level ──
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
      'categories', to_jsonb(COALESCE(c.categories, ARRAY[]::text[])),
      'area', c.area,
      'anonymous', COALESCE(c.anonymous, true),
      'risk_level', COALESCE(c.risk_level, 'medium'),
      'assigned_to', c.assigned_to,
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

GRANT EXECUTE ON FUNCTION public.listar_casos_tenant(TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.listar_casos_tenant(TEXT) TO authenticated;
