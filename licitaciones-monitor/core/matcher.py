"""
Motor de matching y scoring de keywords contra licitaciones.
Soporta operadores AND/OR, sinónimos y scoring por relevancia.
"""
import re
from dataclasses import dataclass
from typing import Optional


# Sinónimos y términos relacionados por categoría forense
SYNONYMS: dict[str, list[str]] = {
    "forense": ["forense", "forenses", "pericia", "pericias", "criminalística"],
    "laboratorio": ["laboratorio", "laboratorios", "lab"],
    "dna": ["adn", "dna", "genético", "genómica"],
    "balística": ["balística", "balistica", "proyectil", "armas"],
    "software": ["software", "sistema", "aplicación", "plataforma", "programa"],
    "caligrafo": ["calígrafo", "caligrafo", "grafologo", "grafólogo", "grafología", "caligrafía"],
    "investigacion": ["investigación", "investigacion", "indagatoria"],
}


@dataclass
class MatchResult:
    matched: bool
    keywords_found: list[str]
    score: float
    highlights: list[str]


class KeywordMatcher:
    """
    Evalúa si un texto es relevante para una lista de keywords.

    Características:
    - Búsqueda case-insensitive
    - Normalización de caracteres especiales (tildes)
    - Expansión por sinónimos
    - Operadores AND/OR
    - Scoring por posición (título > descripción) y frecuencia
    """

    def __init__(self, keywords: list[str], operator: str = "OR"):
        """
        operator: "OR" = al menos una keyword debe matchear
                  "AND" = todas las keywords deben matchear
        """
        self.raw_keywords = keywords
        self.operator = operator.upper()
        self.patterns = self._compile_patterns(keywords)

    def match(
        self,
        titulo: str,
        descripcion: Optional[str] = None,
        organismo: Optional[str] = None,
    ) -> MatchResult:
        """
        Evalúa relevancia de un texto contra las keywords configuradas.
        Retorna MatchResult con score y keywords encontradas.
        """
        # Normalizar textos
        titulo_norm = self._normalize(titulo or "")
        desc_norm = self._normalize(descripcion or "")
        org_norm = self._normalize(organismo or "")

        all_text = f"{titulo_norm} {desc_norm} {org_norm}"

        keywords_found = []
        highlights = []

        for kw, pattern in self.patterns.items():
            # Titulo tiene más peso (factor 2)
            in_titulo = bool(pattern.search(titulo_norm))
            in_desc = bool(pattern.search(desc_norm))
            in_org = bool(pattern.search(org_norm))

            if in_titulo or in_desc or in_org:
                keywords_found.append(kw)
                if in_titulo:
                    highlights.append(f"título: '{self._find_context(titulo_norm, pattern)}'")

        # Determinar si matchea según operador
        if self.operator == "AND":
            matched = len(keywords_found) == len(self.raw_keywords)
        else:  # OR
            matched = len(keywords_found) > 0

        # Calcular score
        score = self._compute_score(
            keywords_found, titulo_norm, desc_norm, all_text
        )

        return MatchResult(
            matched=matched,
            keywords_found=keywords_found,
            score=score,
            highlights=highlights,
        )

    def _compile_patterns(self, keywords: list[str]) -> dict[str, re.Pattern]:
        """Compila regex por cada keyword, incluyendo sinónimos."""
        patterns = {}
        for kw in keywords:
            kw_norm = self._normalize(kw)
            # Obtener sinónimos
            synonyms = self._get_synonyms(kw_norm)
            all_terms = list(set([kw_norm] + synonyms))
            # Crear patrón que matchee cualquier sinónimo como palabra completa
            regex = "|".join(
                r"\b" + re.escape(term) + r"\b" for term in all_terms
            )
            try:
                patterns[kw] = re.compile(regex, re.IGNORECASE | re.UNICODE)
            except re.error:
                # Si falla, usar búsqueda simple
                patterns[kw] = re.compile(re.escape(kw_norm), re.IGNORECASE)
        return patterns

    def _get_synonyms(self, keyword: str) -> list[str]:
        """Retorna sinónimos para una keyword."""
        for key, syns in SYNONYMS.items():
            if keyword in syns or key in keyword:
                return [s for s in syns if s != keyword]
        return []

    @staticmethod
    def _normalize(text: str) -> str:
        """
        Normaliza texto: minúsculas + reemplaza tildes.
        No elimina tildes para evitar falsos positivos,
        pero construye versión sin tildes para búsqueda flexible.
        """
        replacements = {
            "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
            "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u",
            "ü": "u", "Ü": "u", "ñ": "n", "Ñ": "n",
        }
        result = text.lower()
        for accent, plain in replacements.items():
            result = result.replace(accent, plain)
        return result

    def _compute_score(
        self,
        found_keywords: list[str],
        titulo: str,
        descripcion: str,
        full_text: str,
    ) -> float:
        """
        Score de relevancia 0.0-1.0.
        - Más keywords encontradas = mayor score
        - Keywords en título = doble peso
        - Frecuencia en texto = bonus
        """
        if not found_keywords:
            return 0.0

        base_score = len(found_keywords) / max(len(self.raw_keywords), 1)

        # Bonus por keywords en título
        titulo_bonus = 0.0
        for kw, pattern in self.patterns.items():
            if kw in found_keywords and pattern.search(titulo):
                titulo_bonus += 0.1

        # Bonus por frecuencia total
        total_matches = sum(
            len(pattern.findall(full_text))
            for kw, pattern in self.patterns.items()
            if kw in found_keywords
        )
        freq_bonus = min(total_matches * 0.02, 0.2)

        return min(base_score + titulo_bonus + freq_bonus, 1.0)

    @staticmethod
    def _find_context(text: str, pattern: re.Pattern, context_chars: int = 40) -> str:
        """Extrae contexto alrededor del match para highlight."""
        match = pattern.search(text)
        if not match:
            return ""
        start = max(0, match.start() - context_chars)
        end = min(len(text), match.end() + context_chars)
        return ("..." if start > 0 else "") + text[start:end] + ("..." if end < len(text) else "")
