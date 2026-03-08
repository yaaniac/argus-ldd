-- ============================================================
-- Argus LDD · Supabase · Schema inicial
-- Ejecutar en SQL Editor del proyecto Supabase
-- ============================================================

-- Extensión para generar códigos únicos (opcional, usamos sequence)
-- CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Tenants (empresas) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.tenants (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug       TEXT NOT NULL UNIQUE,
  name       TEXT NOT NULL,
  config     JSONB DEFAULT '{}',
  pin_hash   TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenants_slug ON public.tenants(slug);

-- ── Casos (denuncias) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.casos (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  tracking_code    TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'closed')),
  category         TEXT,
  categories       TEXT[],
  description     TEXT,
  area             TEXT,
  anonymous        BOOLEAN DEFAULT true,
  contact_name     TEXT,
  contact_email    TEXT,
  contact_phone    TEXT,
  metadata         JSONB DEFAULT '{}',
  created_at       TIMESTAMPTZ DEFAULT now(),
  updated_at       TIMESTAMPTZ DEFAULT now(),
  UNIQUE(tenant_id, tracking_code)
);

CREATE INDEX IF NOT EXISTS idx_casos_tenant ON public.casos(tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_casos_tracking ON public.casos(tracking_code);
CREATE INDEX IF NOT EXISTS idx_casos_status ON public.casos(status);
CREATE INDEX IF NOT EXISTS idx_casos_created ON public.casos(created_at DESC);

-- ── Mensajes de seguimiento (para el denunciante) ─────────────
CREATE TABLE IF NOT EXISTS public.caso_seguimiento (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  caso_id    UUID NOT NULL REFERENCES public.casos(id) ON DELETE CASCADE,
  title      TEXT,
  message    TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seguimiento_caso ON public.caso_seguimiento(caso_id);

-- ── RLS: activar por tabla ──────────────────────────────────
ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.casos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.caso_seguimiento ENABLE ROW LEVEL SECURITY;

-- Políticas: anónimos no leen/escriben directo en tablas.
-- Solo vía funciones RPC.

-- Tenants: nadie lee por anon (solo usamos en RPC con SECURITY DEFINER)
CREATE POLICY "tenants_no_anon" ON public.tenants FOR ALL USING (false);

-- Casos: solo lectura para usuarios autenticados del backoffice (lo haremos después)
CREATE POLICY "casos_no_anon" ON public.casos FOR ALL USING (false);

-- Seguimiento: idem
CREATE POLICY "seguimiento_no_anon" ON public.caso_seguimiento FOR ALL USING (false);

-- ── Función: crear denuncia (anon) ────────────────────────────
CREATE OR REPLACE FUNCTION public.crear_denuncia(
  p_tenant_slug    TEXT,
  p_category       TEXT DEFAULT NULL,
  p_categories     TEXT[] DEFAULT NULL,
  p_description    TEXT DEFAULT NULL,
  p_area           TEXT DEFAULT NULL,
  p_anonymous      BOOLEAN DEFAULT true,
  p_contact_name    TEXT DEFAULT NULL,
  p_contact_email  TEXT DEFAULT NULL,
  p_contact_phone   TEXT DEFAULT NULL,
  p_metadata       JSONB DEFAULT '{}'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_tenant_id   UUID;
  v_year         INT;
  v_seq          INT;
  v_code         TEXT;
  v_caso_id      UUID;
BEGIN
  -- Resolver tenant
  SELECT id INTO v_tenant_id FROM public.tenants WHERE slug = p_tenant_slug LIMIT 1;
  IF v_tenant_id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Tenant no encontrado');
  END IF;

  -- Generar código único ARG-YYYY-XXXX
  v_year := EXTRACT(YEAR FROM now())::INT;
  SELECT COALESCE(MAX(
    NULLIF(SUBSTRING(tracking_code FROM 10 FOR 4), '')::INT
  ), 0) + 1 INTO v_seq
  FROM public.casos
  WHERE tenant_id = v_tenant_id
    AND tracking_code LIKE 'ARG-' || v_year || '-%';

  v_code := 'ARG-' || v_year || '-' || LPAD(v_seq::TEXT, 4, '0');

  INSERT INTO public.casos (
    tenant_id, tracking_code, status, category, categories,
    description, area, anonymous, contact_name, contact_email, contact_phone, metadata
  ) VALUES (
    v_tenant_id, v_code, 'pending', p_category, p_categories,
    p_description, p_area, p_anonymous, p_contact_name, p_contact_email, p_contact_phone, p_metadata
  )
  RETURNING id INTO v_caso_id;

  RETURN jsonb_build_object('ok', true, 'tracking_code', v_code, 'id', v_caso_id);
END;
$$;

-- ── Función: consultar seguimiento (anon, solo por código) ────
CREATE OR REPLACE FUNCTION public.get_seguimiento(p_tracking_code TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_caso    RECORD;
  v_msg     RECORD;
  v_status  TEXT;
  v_label   TEXT;
  v_result  JSONB;
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

  v_status := v_caso.status;
  v_label  := CASE v_status
    WHEN 'pending' THEN 'Pendiente de evaluación'
    WHEN 'active'  THEN 'En investigación'
    WHEN 'closed'  THEN 'Resuelto'
    ELSE v_status
  END;

  SELECT title, message, created_at INTO v_msg
  FROM public.caso_seguimiento
  WHERE caso_id = v_caso.id
  ORDER BY created_at DESC
  LIMIT 1;

  v_result := jsonb_build_object(
    'ok', true,
    'found', true,
    'tracking_code', v_caso.tracking_code,
    'status', v_status,
    'label', v_label,
    'date', to_char(v_caso.updated_at, 'DD Mon YYYY — HH24:MI') || ' hs',
    'created_at', v_caso.created_at
  );

  IF v_msg.title IS NOT NULL OR v_msg.message IS NOT NULL THEN
    v_result := v_result || jsonb_build_object(
      'msg', jsonb_build_object('title', v_msg.title, 'text', v_msg.message)
    );
  END IF;

  RETURN v_result;
END;
$$;

-- Permisos para anon y authenticated
GRANT EXECUTE ON FUNCTION public.crear_denuncia TO anon;
GRANT EXECUTE ON FUNCTION public.crear_denuncia TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_seguimiento TO anon;
GRANT EXECUTE ON FUNCTION public.get_seguimiento TO authenticated;

-- ── Seed opcional: tenant demo ──────────────────────────────
INSERT INTO public.tenants (slug, name, config)
VALUES ('demo', 'Demo', '{}')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO public.tenants (slug, name, config)
VALUES ('acme', 'Acme', '{}')
ON CONFLICT (slug) DO NOTHING;
