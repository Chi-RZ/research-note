# Quimb gate ordering dependency

Quimb 1.15.0 imports `networkx` when constructing automatic gate orderings, so
declare it directly in reproducible environments even when the base Quimb
installation succeeds without it. Source: `peps_simple_update/node` `01.001`.
