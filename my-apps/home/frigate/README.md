# Frigate with Google Nest Camera Integration

This document outlines the configuration for running Frigate and integrating it with modern (post-2021) Google Nest cameras that use the WebRTC protocol.

## Overview

The integration uses Frigate's bundled `go2rtc` service to connect directly to the Google Smart Device Management (SDM) API. This method is the most reliable and performant, as it bypasses Home Assistant for the camera streams and connects directly to the source.

The setup involves three main components:
1.  **Kubernetes Secrets**: An `ExternalSecret` is used to securely pull the necessary API credentials from a 1Password vault.
2.  **Frigate Deployment**: The deployment is configured to pass these credentials as environment variables to the Frigate container.
3.  **Frigate `config.yml`**: The configuration file defines the `go2rtc` streams using the `nest:` provider, which uses the environment variables to authenticate with Google's API.

## Credentials and Setup Process

This integration requires a one-time, manual setup process to obtain the necessary credentials from Google.

### Required Credentials

The following credentials must be obtained and stored in a `frigate` item in a 1Password vault:

| 1Password Field        | Description                                     | Origin                           |
| ---------------------- | ----------------------------------------------- | -------------------------------- |
| `nest_client_id`       | OAuth 2.0 Client ID for your web application.   | Google Cloud Console             |
| `nest_client_secret`   | OAuth 2.0 Client Secret for your web application. | Google Cloud Console             |
| `nest_project_id`      | The unique ID for your Device Access project.   | Google Device Access Console     |
| `nest_refresh_token`   | A permanent token to re-authenticate with Google. | Manual OAuth2 OOB Flow           |

### Setup Guide

The definitive guide for this process can be found in the official Frigate GitHub discussions:
[**Nest Cam -> Frigate (Integrated go2rtc) Setup Workflow**](https://github.com/blakeblackshear/frigate/discussions/17527)

Follow **Phase 2, 3, and 4** of that guide carefully. Key steps include:
1.  Creating a Google Cloud Project and enabling the "Smart Device Management API".
2.  Configuring the OAuth Consent Screen and creating an OAuth Client ID.
3.  Creating a Device Access Project and linking it to your Google Cloud project ($5 fee required).
4.  Setting the OAuth app's **Publishing status** to **In production** to ensure the refresh token does not expire.
5.  Performing the manual "Out-of-Band" (OOB) authentication flow with a `curl` command to get the `refresh_token`.
6.  Using a temporary `access_token` to list devices and retrieve the unique `device_id` for each camera.

## Kubernetes Configuration Files

-   **`externalsecret.yaml`**: Defines the `ExternalSecret` resource that maps the credentials from the `frigate` item in 1Password to a native Kubernetes `Secret` named `frigate-secrets`.
-   **`deployment.yaml`**: Mounts the data from the `frigate-secrets` Secret as environment variables (e.g., `FRIGATE_NEST_CLIENT_ID`) into the Frigate container.
-   **`config.yml`**: Contains the primary Frigate configuration. The `go2rtc.streams` section is populated with the `nest:` provider string, which includes placeholders for the environment variables and the unique `device_id` for each camera.

This setup ensures that no sensitive credentials are hardcoded in the repository, adhering to GitOps best practices. 