# Paired MiniHR releases

These modules are generic copies of the private Site's shared/minihr source.
Every functionality change must be applied/tested in both hosts, or explicitly
recorded as pending. Use the Site's scripts/sync_minihr_to_gestionale.py and
--check; do not hand-edit the manifest to conceal a mismatch. Run the shared
Node tests and HR adapter tests. Production ERP activation remains a separate
reviewed checkpoint; keep the Site active during transition.

Never copy payroll JSON, PDF, real fiscal codes, Site dist, credentials or
financial snapshots into this PUBLIC repository. Host-specific adapters stay
separate. No automatic accounting migration or silent changes to balances,
assignments, stable IDs, or persistent exclusions.
