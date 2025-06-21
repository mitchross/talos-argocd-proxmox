# Argo CD Upgrade to v3.0

This document outlines the process for upgrading Argo CD to version 3.0, including key changes, rollback procedures, and updated configurations.

## Upgrade Process

The upgrade is managed through GitOps by updating the Helm chart version in `infrastructure/controllers/argocd/kustomization.yaml`.

1.  **Update Helm Chart**: The `version` in `kustomization.yaml` was updated to `8.1.1`, which corresponds to Argo CD application version `v3.0.6`.
2.  **Apply Manifests**: The changes were applied by committing the updated files to the Git repository, which Argo CD then automatically syncs.

## Key Changes and Resolutions

### 1. RBAC Permissions

-   **Change**: Argo CD v3.0 requires more explicit RBAC permissions. The `*` wildcard is no longer sufficient for many resources.
-   **Resolution**: The `projects.yaml` file was updated to define more granular permissions for the `infrastructure`, `monitoring`, and `my-apps` projects. Wildcards were replaced with specific resource groups and kinds where possible. A `troubleshooting` role was added to the `monitoring` and `my-apps` projects to allow `exec` into pods.

### 2. Resource Tracking

-   **Change**: The default resource tracking method is now `annotation`.
-   **Resolution**: The `application.resourceTrackingMethod` in `values.yaml` is set to `annotation+label` to ensure backward compatibility with existing resources.

### 3. Insecure Server

-   **Change**: The `server.insecure: true` flag was previously used.
-   **Resolution**: This was initially going to be replaced with a TLS certificate, but per your request, we are continuing to use an insecure connection for now.

## Rollback Procedure

To roll back the upgrade, revert the changes in the Git repository. Specifically:

1.  Revert the `version` in `infrastructure/controllers/argocd/kustomization.yaml` to the previous version.
2.  Revert the changes to `infrastructure/controllers/argocd/values.yaml` and `infrastructure/controllers/argocd/projects.yaml`.
3.  Commit and push the changes to the Git repository. Argo CD will automatically sync and roll back to the previous version. 