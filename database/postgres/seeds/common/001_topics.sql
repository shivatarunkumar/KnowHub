-- Default topic list for every environment. Idempotent: re-running updates names,
-- descriptions and order but never deletes topics an admin added.

INSERT INTO topics (slug, name, description, icon, sort_order) VALUES
    ('gcp',            'GCP',             'Projects, quotas, billing, ADC and anything cross-service', 'cloud',  5),
    ('bigquery',       'BigQuery',        'Data warehouse, SQL, slots, partitioning, cost',        'database',  10),
    ('pubsub',         'Pub/Sub',         'Messaging, subscriptions, ordering, dead letters',      'message',   20),
    ('gke',            'GKE',             'Kubernetes clusters, workloads, autoscaling',           'cluster',   30),
    ('cloud-run',      'Cloud Run',       'Serverless containers, revisions, cold starts',         'run',       40),
    ('cloud-sql',      'Cloud SQL',       'Managed Postgres/MySQL, connections, replicas',         'database',  50),
    ('cloud-storage',  'Cloud Storage',   'Buckets, lifecycle, signed URLs, IAM',                  'bucket',    60),
    ('dataflow',       'Dataflow',        'Beam pipelines, streaming and batch jobs',              'flow',      70),
    ('composer',       'Composer',        'Airflow DAGs, scheduling, operators',                   'schedule',  80),
    ('iam',            'IAM & Security',  'Roles, service accounts, secrets, org policies',        'shield',    90),
    ('networking',     'Networking',      'VPC, load balancers, DNS, firewall rules',              'network',  100),
    ('monitoring',     'Monitoring',      'Logging, metrics, alerting, tracing',                   'chart',    110),
    ('ci-cd',          'CI/CD',           'Cloud Build, Artifact Registry, deployments',           'pipeline', 120),
    -- anything that doesn't belong to one GCP service
    ('terraform',      'Terraform',       'Modules, state, plans, drift',                          'infra',    130),
    ('kubernetes',     'Kubernetes',      'Manifests, operators, debugging pods (any cluster)',    'cluster',  140),
    ('docker',         'Docker',          'Images, builds, registries, local containers',          'container',150),
    ('python',         'Python',          'Services, scripts, packaging, performance',             'code',     160),
    ('sql',            'SQL',             'Queries, tuning, modelling, migrations',                'database', 170),
    ('kafka',          'Kafka',           'Topics, consumer groups, lag, rebalancing',             'message',  180),
    ('spark',          'Spark',           'Jobs, partitions, shuffles, tuning',                    'flow',     190),
    ('git',            'Git & GitHub',    'Branching, reviews, actions, release flow',             'branch',   200),
    ('incidents',      'Incident response','Sev handling, comms, postmortems, war rooms',          'alert',    210),
    ('ai',             'AI & ML',         'Models, prompts, embeddings, evaluation',               'sparkle',  220),
    ('frontend',       'Frontend',        'Web apps, browser debugging, build tooling',            'browser',  230),
    ('other',          'Other',           'Anything that doesn''t fit the topics above',           'dots',     900)
ON CONFLICT (slug) DO UPDATE SET
    name        = EXCLUDED.name,
    description = EXCLUDED.description,
    icon        = EXCLUDED.icon,
    sort_order  = EXCLUDED.sort_order;
