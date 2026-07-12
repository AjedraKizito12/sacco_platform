// Mirrors app/core/search/schemas.py.
export interface SearchHitOut {
  entity_type: string;
  id: string;
  title: string;
  subtitle: string;
  url: string;
  status: string;
  status_entity: string;
}

export interface SearchResultsOut {
  hits: SearchHitOut[];
  took_ms: number;
}
