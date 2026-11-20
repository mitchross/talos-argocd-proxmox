# Homelab Rack Planner

Plans a 10-inch rack in the browser. Public at https://homelab.vanillax.me (GET only, through Cloudflare); the LAN route also works.

Source: https://gitea.vanillax.me/vanillax/homelab-rack-planner. Every push to its `main` builds `registry.vanillax.me/homelab-rack-planner:vX.Y.Z`. Renovate opens the bump PR here.

Static files only, served by static-web-server (Rust), so there is no storage, secret or backup. The HTTPRoutes send `/ds/api/listings` to deal-scout (operator view on the LAN, public view on the internet; `ReferenceGrant` in `deal-scout/`) and keep `/private/` (real Wi-Fi names) off the public route.
