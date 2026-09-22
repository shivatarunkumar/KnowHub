-- Teams for a retail and commercial bank. Idempotent: re-running updates names,
-- descriptions and order but never deletes a team an admin added.

INSERT INTO teams (slug, name, description, division, sort_order) VALUES
    ('payments',        'Payments',              'Faster Payments, SEPA, SWIFT, standing orders and direct debits', 'Banking Platform',  10),
    ('cards',           'Cards',                 'Debit and credit card issuing, authorisations, chargebacks',      'Banking Platform',  20),
    ('core-banking',    'Core Banking',          'Accounts, balances, ledgers, end-of-day batch',                    'Banking Platform',  30),
    ('lending',         'Lending & Mortgages',   'Applications, affordability, underwriting, servicing',            'Lending',           40),
    ('retail-banking',  'Retail Banking',        'Current accounts, savings, everyday banking journeys',            'Customer',          50),
    ('digital-channels','Digital Channels',      'Mobile app, internet banking, notifications, accessibility',      'Customer',          60),
    ('wealth',          'Wealth & Investments',  'Portfolios, ISAs, pensions, market data feeds',                    'Customer',          70),
    ('fraud',           'Fraud & Financial Crime', 'Transaction monitoring, AML, sanctions screening, KYC',         'Risk',              80),
    ('risk-compliance', 'Risk & Compliance',     'Credit risk models, controls, audit evidence, policy',            'Risk',              90),
    ('risk-foundation', 'Risk Foundation',       'Shared risk data, models and services the other risk teams build on', 'Risk',         92),
    ('credit-risk',     'Credit Risk',           'PD/LGD/EAD models, scorecards, IFRS 9 impairment',                'Risk',              94),
    ('enterprise-risk', 'Enterprise Risk',       'Risk appetite, operational risk, stress testing, ICAAP',          'Risk',              96),
    ('credit-platform', 'Credit Platform',       'Decisioning engine, limits, exposure and credit data services',   'Risk',              98),
    ('regulatory',      'Regulatory Reporting',  'BCBS 239, COREP/FINREP, transaction reporting, submissions',      'Finance',          100),
    ('finance',         'Finance & Treasury',    'General ledger, liquidity, funding, month-end close',              'Finance',          110),
    ('data-platform',   'Data Platform',         'Warehouse, pipelines, data quality, lineage and governance',      'Technology',       120),
    ('sre',             'SRE & Infrastructure',  'Reliability, on-call, capacity, incident response',                'Technology',       130),
    ('security',        'Security Engineering',  'Identity, secrets, vulnerability management, pen-test fixes',     'Technology',       140)
ON CONFLICT (slug) DO UPDATE SET
    name        = EXCLUDED.name,
    description = EXCLUDED.description,
    division    = EXCLUDED.division,
    sort_order  = EXCLUDED.sort_order;
