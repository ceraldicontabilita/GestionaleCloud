# Shared MiniHR contract

Generic buildless ES modules, also used by the private Site. No personal or
financial source data belongs here. Host adapters are separate.

Run `node --test frontend_shared/minihr/core.test.mjs`. The SHA256 manifest
must match the Site's `shared/minihr/manifest.json`; use its allowlisted sync
script for every shared change, never copy the Site `dist` directory.

DTO v1: employees have stable `id`, `name`, explicit relationship `events`,
`slips`, `payments`, and document-only `documents`. Money uses integer cents;
unreadable amounts are null, not zero. A document-only PDF never changes a
balance. Year exclusions affect both payroll and payments, not visibility.
Different host accounting sources must be labeled, never silently merged.

The custom element emits a cancelable `minihr-document` event for authenticated
host downloads; `minihr-employee` reports selection. Only host code performs
network or storage operations. Core and view have no DB writes.
