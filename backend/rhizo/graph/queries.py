from rhizo.core.validate import check_hops

TOPOLOGY_INDEXES = (
    "CREATE INDEX FOR (s:Service) ON (s.name)",
    "CREATE INDEX FOR (r:Resource) ON (r.name)",
    "CREATE INDEX FOR (e:Engineer) ON (e.handle)",
    "CREATE INDEX FOR (f:File) ON (f.path)",
    "CREATE INDEX FOR (c:Commit) ON (c.sha)",
)

MEMORY_INDEXES = (
    "CREATE INDEX FOR (i:Incident) ON (i.id)",
    "CREATE INDEX FOR (s:Service) ON (s.name)",
    "CREATE INDEX FOR (r:Resource) ON (r.name)",
    "CREATE INDEX FOR (e:Engineer) ON (e.handle)",
)


COUNT_SERVICES = "MATCH (s:Service) RETURN count(s)"
COUNT_LIVE_EDGES = "MATCH ()-[r:DEPENDS_ON|USES|CO_CHANGES_WITH]->() WHERE r.valid_to IS NULL RETURN count(r)"
COUNT_INCIDENTS = "MATCH (i:Incident) RETURN count(i)"


DELETE_VANISHED_NODES = """
MATCH (n) WHERE (n:Service OR n:Resource) AND NOT n.name IN $names
DETACH DELETE n
RETURN count(n)
"""

UPSERT_SERVICES = """
UNWIND $rows AS row
MERGE (s:Service {name: row.name})
ON CREATE SET s.tier = 2
RETURN count(s)
"""

UPSERT_RESOURCES = """
UNWIND $rows AS row
MERGE (r:Resource {name: row.name})
SET r.kind = row.kind
RETURN count(r)
"""

_UPSERT_EDGES = """
UNWIND $rows AS row
MATCH (a:Service {{name: row.source}}), (b:{target} {{name: row.target}})
MERGE (a)-[r:{rel}]->(b)
ON CREATE SET r.source = $source, r.confidence = $confidence, r.valid_from = $now
ON MATCH SET
  r.confidence = CASE WHEN $source = 'declared' AND r.source <> 'declared' AND r.confidence < $confidence
                      THEN $confidence ELSE r.confidence END,
  r.source = CASE WHEN $source = 'declared' THEN 'declared' ELSE r.source END,
  r.valid_from = CASE WHEN r.valid_to IS NULL THEN r.valid_from ELSE $now END
SET r.evidence = row.evidence, r.last_seen = $now, r.valid_to = null
RETURN count(r)
"""
UPSERT_DEPENDS_ON = _UPSERT_EDGES.format(rel="DEPENDS_ON", target="Service")
UPSERT_USES = _UPSERT_EDGES.format(rel="USES", target="Resource")

EXPIRE_VANISHED_DETECTED = """
MATCH (a:Service)-[r:DEPENDS_ON|USES]->(b)
WHERE r.source IN $sources AND r.valid_to IS NULL AND NOT ((type(r) + ':' + a.name + '->' + b.name) IN $seen)
SET r.valid_to = $now
RETURN count(r)
"""

EXPIRE_STALE_INFERRED = """
MATCH ()-[r:DEPENDS_ON|USES|CO_CHANGES_WITH]->()
WHERE r.valid_to IS NULL AND NOT r.source IN ['declared', 'code'] AND r.last_seen < $cutoff
SET r.valid_to = $now
RETURN count(r)
"""


_LIVE = (
    "(($as_of IS NULL AND x.valid_to IS NULL) OR "
    "($as_of IS NOT NULL AND x.valid_from <= $as_of AND (x.valid_to IS NULL OR x.valid_to > $as_of)))"
)
_PATH_FILTER = f"all(x IN relationships(p) WHERE {_LIVE} AND x.confidence >= $min_conf)"
_PATH_RETURN = """[n IN nodes(p) | n.name] AS path,
       [x IN relationships(p) | x.source] AS sources,
       reduce(c = 1.0, x IN relationships(p) | c * x.confidence) AS path_conf"""

ROOT_LABELS = """
UNWIND $names AS name
OPTIONAL MATCH (s:Service {name: name})
OPTIONAL MATCH (r:Resource {name: name})
RETURN name, s IS NOT NULL AS is_service, r IS NOT NULL AS is_resource
"""

DEPENDS_ON_DEGREE = f"""
MATCH (s:Service) WHERE s.name IN $names
OPTIONAL MATCH (s)-[x:DEPENDS_ON]-() WHERE {_LIVE}
RETURN s.name, count(x)
"""


def blast_radius_services(max_hops: int) -> str:
    n = check_hops(max_hops)
    return f"""
MATCH p = (v:Service)-[:DEPENDS_ON*1..{n}]->(s:Service)
WHERE s.name IN $names AND NOT v.name IN $failed AND {_PATH_FILTER}
RETURN v.name AS victim, {_PATH_RETURN}
"""


def blast_radius_resources(max_hops: int) -> str:
    n = check_hops(max_hops)
    return f"""
MATCH p = (v:Service)-[:DEPENDS_ON*0..{n - 1}]->(:Service)-[:USES]->(r:Resource)
WHERE r.name IN $names AND NOT v.name IN $failed AND {_PATH_FILTER}
RETURN v.name AS victim, {_PATH_RETURN}
"""


CONNECTIVITY_FALLBACK = f"""
MATCH (s:Service)-[a:USES]->(:Resource)<-[b:USES]-(v:Service)
WHERE s.name IN $names AND NOT v.name IN $failed
  AND all(x IN [a, b] WHERE {_LIVE} AND x.confidence >= $min_conf)
RETURN v.name AS victim, s.name AS root, a.confidence * b.confidence AS conf
UNION ALL
MATCH (s:Service)-[c:CO_CHANGES_WITH]-(v:Service)
WHERE s.name IN $names AND NOT v.name IN $failed
  AND all(x IN [c] WHERE {_LIVE} AND x.confidence >= $min_conf)
RETURN v.name AS victim, s.name AS root, c.confidence AS conf
"""


def upstream_suspects(max_hops: int) -> str:
    n = check_hops(max_hops)
    return f"""
MATCH p = (s:Service {{name: $name}})-[:DEPENDS_ON*1..{n}]->(u:Service)
WHERE u.name <> $name AND {_PATH_FILTER}
OPTIONAL MATCH (u)<-[:PART_OF]-(:File)<-[:TOUCHED]-(c:Commit)
WHERE c.ts >= $since
RETURN u.name AS suspect, count(DISTINCT c) AS recent_commits, {_PATH_RETURN}
"""


SERVICE_NODES = """
MATCH (s:Service) WHERE $names IS NULL OR s.name IN $names
RETURN s.name, s.tier, s.language, s.repo, s.path_prefix, null
ORDER BY s.name
"""

RESOURCE_NODES = """
MATCH (r:Resource)
RETURN r.name, r.kind
ORDER BY r.name
"""

GRAPH_EDGES = """
MATCH (a)-[r:DEPENDS_ON|USES|CO_CHANGES_WITH]->(b)
RETURN type(r), labels(a)[0], a.name, labels(b)[0], b.name,
       r.source, r.confidence, r.valid_from, r.valid_to, r.evidence
"""

SERVICE_OWNERS = """
MATCH (e:Engineer)-[c:COMMITTED_TO]->(:Service {name: $name})
RETURN e.handle, e.name, c.count, e.pseudonymous
ORDER BY c.count DESC, e.handle
LIMIT $limit
"""


GET_VERSION = "MATCH (m:Meta {key: 'graph'}) RETURN m.version"

BUMP_VERSION = """
MERGE (m:Meta {key: 'graph'})
ON CREATE SET m.version = 0
SET m.version = m.version + 1, m.ingested_at = $now
RETURN m.version
"""

HIDDEN_MAX_HOPS = 4


def _not_connected(carry: str) -> str:
    return f"""
OPTIONAL MATCH fwd = (a)-[:DEPENDS_ON*1..{HIDDEN_MAX_HOPS}]->(b)
WHERE all(x IN relationships(fwd) WHERE x.valid_to IS NULL)
WITH a, b, {carry}, count(fwd) AS n_fwd
OPTIONAL MATCH back = (b)-[:DEPENDS_ON*1..{HIDDEN_MAX_HOPS}]->(a)
WHERE all(x IN relationships(back) WHERE x.valid_to IS NULL)
WITH a, b, {carry}, n_fwd, count(back) AS n_back
WHERE n_fwd = 0 AND n_back = 0"""


HIDDEN_SHARED_RESOURCE = f"""
MATCH (a:Service)-[ua:USES]->(r:Resource)<-[ub:USES]-(b:Service)
WHERE a.name < b.name AND ua.valid_to IS NULL AND ub.valid_to IS NULL
  AND ($name IS NULL OR a.name = $name OR b.name = $name)
WITH DISTINCT a, b, r
{_not_connected("r")}
RETURN a.name, b.name, r.name, r.kind
"""

HIDDEN_CO_CHANGE = f"""
MATCH (a:Service)-[c:CO_CHANGES_WITH]->(b:Service)
WHERE c.valid_to IS NULL AND c.confidence >= $min_conf
  AND ($name IS NULL OR a.name = $name OR b.name = $name)
WITH a, b, c
{_not_connected("c")}
RETURN a.name, b.name, c.support, c.jaccard, c.confidence
"""


SET_SERVICE_DETAILS = """
UNWIND $rows AS row
MATCH (s:Service {name: row.name})
SET s.path_prefix = row.prefix, s.language = row.language, s.detected_by = row.detected_by, s.repo = $repo
RETURN count(s)
"""

SET_TIERS = """
UNWIND $rows AS row
MATCH (s:Service {name: row.name})
SET s.tier = row.tier, s.tier_basis = row.basis
RETURN count(s)
"""

UPSERT_COMMITS = """
UNWIND $rows AS row
MERGE (c:Commit {sha: row.sha})
SET c.ts = row.ts, c.message = row.message, c.files_count = row.files_count, c.bot = row.bot
RETURN count(c)
"""

UPSERT_FILES = """
UNWIND $rows AS row
MERGE (f:File {path: row.path})
RETURN count(f)
"""

UPSERT_PART_OF = """
UNWIND $rows AS row
MATCH (f:File {path: row.path}), (s:Service {name: row.service})
MERGE (f)-[r:PART_OF]->(s)
RETURN count(r)
"""

UPSERT_TOUCHED = """
UNWIND $rows AS row
MATCH (c:Commit {sha: row.sha}), (f:File {path: row.path})
MERGE (c)-[r:TOUCHED]->(f)
RETURN count(r)
"""

UPSERT_ENGINEERS = """
UNWIND $rows AS row
MERGE (e:Engineer {handle: row.handle})
SET e.name = row.name, e.pseudonymous = row.pseudonymous
RETURN count(e)
"""

UPSERT_AUTHORED = """
UNWIND $rows AS row
MATCH (e:Engineer {handle: row.handle}), (c:Commit {sha: row.sha})
MERGE (e)-[r:AUTHORED]->(c)
RETURN count(r)
"""

SET_COMMITTED_TO = """
UNWIND $rows AS row
MATCH (e:Engineer {handle: row.handle}), (s:Service {name: row.service})
MERGE (e)-[r:COMMITTED_TO]->(s)
SET r.count = row.count, r.last_at = row.last_at
RETURN count(r)
"""


COMMIT_SERVICES = """
MATCH (c:Commit)-[:TOUCHED]->(:File)-[:PART_OF]->(s:Service)
WHERE c.files_count <= $max_files AND NOT c.bot
RETURN c.sha, collect(DISTINCT s.name)
"""

UPSERT_CO_CHANGE = """
UNWIND $rows AS row
MATCH (a:Service {name: row.source}), (b:Service {name: row.target})
MERGE (a)-[r:CO_CHANGES_WITH]->(b)
ON CREATE SET r.valid_from = $now
ON MATCH SET r.valid_from = CASE WHEN r.valid_to IS NULL THEN r.valid_from ELSE $now END
SET r.source = 'inferred', r.confidence = row.confidence, r.support = row.support, r.jaccard = row.jaccard,
    r.evidence = row.evidence, r.last_seen = $now, r.valid_to = null
RETURN count(r)
"""

EXPIRE_CO_CHANGE = """
MATCH (a:Service)-[r:CO_CHANGES_WITH]->(b:Service)
WHERE r.valid_to IS NULL AND NOT ((a.name + '->' + b.name) IN $seen)
SET r.valid_to = $now
RETURN count(r)
"""


PAGERANK = """
CALL algo.pageRank('Service', 'DEPENDS_ON') YIELD node, score
RETURN node.name, score
"""

RELATIONSHIP_TYPES = "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"

LABEL_PROPAGATION = """
CALL algo.labelPropagation($config) YIELD node, communityId
RETURN node.name, communityId
"""

SERVICE_DEGREES = """
MATCH (s:Service)
OPTIONAL MATCH (:Service)-[i:DEPENDS_ON]->(s) WHERE i.valid_to IS NULL
WITH s, count(i) AS dependents
OPTIONAL MATCH (s)-[o:DEPENDS_ON]->(:Service) WHERE o.valid_to IS NULL
RETURN s.name, dependents, count(o)
"""


CREATE_INCIDENT = """
OPTIONAL MATCH (x:Incident) WHERE x.id STARTS WITH 'INC-'
WITH coalesce(max(toInteger(substring(x.id, 4))), 100) + 1 AS n
CREATE (i:Incident {id: 'INC-' + toString(n), title: $title, symptom: $symptom, severity: $severity,
                    status: 'open', started_at: $started_at, source: 'manual'})
WITH i
UNWIND $affected AS name
MERGE (s:Service {name: name})
MERGE (i)-[:AFFECTED]->(s)
RETURN DISTINCT i.id
"""

SET_RESOLVED = """
MATCH (i:Incident {id: $id})
SET i.status = 'resolved', i.resolved_at = $now, i.root_cause_text = $root_cause, i.fix = $fix
RETURN i.id
"""

_SET_ROOT_CAUSE = """
UNWIND $rows AS row
MATCH (i:Incident {{id: row.id}})
OPTIONAL MATCH (i)-[old:ROOT_CAUSE]->()
DELETE old
WITH DISTINCT i, row
MERGE (n:{label} {{name: row.name}})
MERGE (i)-[r:ROOT_CAUSE]->(n)
RETURN count(r)
"""
SET_ROOT_CAUSE_SERVICE = _SET_ROOT_CAUSE.format(label="Service")
SET_ROOT_CAUSE_RESOURCE = _SET_ROOT_CAUSE.format(label="Resource")

SET_RESOLVED_BY = """
UNWIND $rows AS row
MATCH (i:Incident {id: row.id})
OPTIONAL MATCH (i)-[old:RESOLVED_BY]->()
DELETE old
WITH DISTINCT i, row
MERGE (e:Engineer {handle: row.handle})
MERGE (i)-[r:RESOLVED_BY]->(e)
RETURN count(r)
"""

RECORD_REVEALED = """
UNWIND $rows AS row
MATCH (i:Incident {id: $id})
MERGE (s:Service {name: row.from})
MERGE (i)-[r:REVEALED {to_service: row.to, edge_type: 'DEPENDS_ON'}]->(s)
RETURN count(r)
"""

INCIDENTS = """
MATCH (i:Incident) WHERE $ids IS NULL OR i.id IN $ids
OPTIONAL MATCH (i)-[:AFFECTED]->(s)
WITH i, collect(DISTINCT s.name) AS affected
OPTIONAL MATCH (i)-[:ROOT_CAUSE]->(rc)
OPTIONAL MATCH (i)-[:RESOLVED_BY]->(e:Engineer)
RETURN i.id, i.title, i.symptom, i.severity, i.status, i.started_at, i.resolved_at, affected,
       coalesce(rc.name, i.root_cause_text), i.fix, e.handle, i.source, i.url
ORDER BY i.started_at DESC
"""

SIMILAR_INCIDENTS = """
MATCH (i:Incident)-[:AFFECTED]->(s:Service)
WHERE s.name IN $names AND ($exclude IS NULL OR i.id <> $exclude)
WITH i, count(DISTINCT s) AS overlap
MATCH (i)-[:AFFECTED]->(all:Service)
WITH i, overlap, count(DISTINCT all) AS total
RETURN i.id, overlap, total
ORDER BY overlap DESC
LIMIT 10
"""

WRITE_BACK_CONFIRMED = """
UNWIND $rows AS row
MATCH (a:Service {name: row.from}), (b:Service {name: row.to})
MERGE (a)-[r:DEPENDS_ON]->(b)
ON CREATE SET r.source = 'inferred', r.confidence = $created_conf, r.valid_from = $now,
              r.incident_id = $incident_id, r.evidence = 'Revealed by ' + $incident_id
ON MATCH SET r.confidence = CASE WHEN r.confidence + $step > 1.0 THEN 1.0 ELSE r.confidence + $step END,
             r.incident_id = $incident_id,
             r.valid_from = CASE WHEN r.valid_to IS NULL THEN r.valid_from ELSE $now END
SET r.valid_to = null, r.last_seen = $now
RETURN count(r)
"""

REFUTE_EDGES = """
UNWIND $rows AS row
MATCH (:Service {name: row.from})-[r:DEPENDS_ON]->(:Service {name: row.to})
SET r.confidence = CASE WHEN r.confidence - $step < $floor THEN $floor ELSE r.confidence - $step END
RETURN count(r)
"""

ENGINEER_EXISTS = "MATCH (e:Engineer {handle: $handle}) RETURN count(e)"


RESPONDER_COMMITS = """
MATCH (e:Engineer)-[c:COMMITTED_TO]->(s:Service)
WHERE s.name IN $names
RETURN e.handle, s.name, c.count, c.last_at
"""

RESPONDER_RESOLUTIONS = """
MATCH (i:Incident)-[:AFFECTED]->(s:Service), (i)-[:RESOLVED_BY]->(e:Engineer)
WHERE s.name IN $names AND i.status = 'resolved'
RETURN e.handle, count(DISTINCT i)
"""

ENGINEER_NODES = """
MATCH (e:Engineer) WHERE e.handle IN $handles
RETURN e.handle, e.name, e.pseudonymous
ORDER BY e.handle
"""

SERVICE_PREFIXES = """
MATCH (s:Service) WHERE s.path_prefix IS NOT NULL
RETURN s.name, s.path_prefix
"""

COUPLED_FILES = """
MATCH (f:File)<-[:TOUCHED]-(c:Commit)-[:TOUCHED]->(g:File)
WHERE f.path IN $paths AND NOT g.path IN $paths AND c.files_count <= $max_files AND NOT c.bot
RETURN g.path, count(DISTINCT c) AS n
ORDER BY n DESC, g.path
LIMIT $limit
"""

SERVICE_FILES = """
MATCH (f:File)-[:PART_OF]->(s:Service)
WHERE s.name IN $names
RETURN f.path
"""

UPSERT_DERIVED_INCIDENTS = """
UNWIND $rows AS row
MERGE (i:Incident {id: row.id})
ON CREATE SET i.title = row.title, i.symptom = row.symptom, i.severity = row.severity, i.status = 'resolved',
              i.started_at = row.started_at, i.resolved_at = row.resolved_at, i.fix = row.fix,
              i.source = row.source, i.url = row.url
WITH i, row
UNWIND row.affected AS name
MERGE (s:Service {name: name})
MERGE (i)-[r:AFFECTED]->(s)
RETURN count(r)
"""
