// Mirrors MAX_RELEVANT_KM in backend/utils/enforcement_scoring.py — the radius
// beyond which a source is excluded from hotspot correlation. Kept here so the
// map's screening circle can't silently disagree with the backend's actual
// cutoff; if that constant changes, change it here too.
export const MAX_RELEVANT_KM = 25
