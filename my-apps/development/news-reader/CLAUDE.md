# News Reader release policy

- Always use plain semantic release tags (`vMAJOR.MINOR.PATCH`) for both the
  frontend and Temporal worker image references. Never use commit-SHA tags,
  digest-only references, `@sha256` suffixes, or `latest` in these manifests.
- Publish and verify each version before opening its deployment PR. Record
  source revisions and verified digests in the PR, outside manifest image values.
- Never overwrite a published version with different contents. Keep old images
  and configuration available while retained worker versions need them.
- Keep the worker's functional promotion gate and its legacy script ConfigMap.
  Image naming does not change pinned-workflow recovery requirements.
