/**
 * Inyecta SUPABASE_URL y SUPABASE_ANON_KEY (env de Render) en supabase-env.js
 * Uso: node scripts/inject-supabase-env.js
 * En Render: se ejecuta en el Build Command antes de publicar.
 */
const fs = require('fs');
const path = require('path');

const url = process.env.SUPABASE_URL || '';
const anonKey = process.env.SUPABASE_ANON_KEY || '';

const out = `/**
 * Generado en build. No editar.
 * Configuración desde variables de entorno (ej. Render).
 */
window.ArgusSupabase = {
  url: ${JSON.stringify(url)},
  anonKey: ${JSON.stringify(anonKey)}
};
`;

const outPath = path.join(__dirname, '..', 'supabase-env.js');
fs.writeFileSync(outPath, out, 'utf8');
console.log('supabase-env.js generado en', outPath);
