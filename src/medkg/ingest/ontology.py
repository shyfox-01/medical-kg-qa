"""Ingestion re-export of the independent OBO transformation library."""
from medkg_data.ontology import Term, load_obo, mondo_ids, orientation, parse_obo

__all__ = ['Term','load_obo','mondo_ids','orientation','parse_obo']
