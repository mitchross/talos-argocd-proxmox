/**
 * PostHog Analytics Injector — Cloudflare Worker
 *
 * Intercepts HTML responses for *.vanillax.me and injects the PostHog JS
 * snippet before </head>. Enables session recording automatically.
 *
 * Deployment: Cloudflare Dashboard > Workers & Pages > Create > paste this script
 * Secret: Add POSTHOG_API_KEY in Worker Settings > Variables & Secrets > Add Secret
 * Route: Add trigger route *.vanillax.me/* in Worker Settings > Triggers > Routes
 *
 * Excluded hosts:
 *   - ingest-posthog.vanillax.me (prevents infinite loop)
 */

const POSTHOG_HOST = "https://ingest-posthog.vanillax.me";

// Hosts that should never get injection
const EXCLUDED_HOSTS = new Set([
  "ingest-posthog.vanillax.me",
  "posthog.vanillax.me",
  "redlib.vanillax.me",
]);

/**
 * Build the PostHog snippet to inject.
 */
function buildSnippet(apiKey) {
  return `
<!-- PostHog Analytics (injected by Cloudflare Worker) -->
<script>
  !function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="init capture register register_once register_for_session unregister unregister_for_session getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey getNextSurveyStep identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException loadToolbar get_property getSessionProperty createPersonProfile opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing debug".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);
  posthog.init('${apiKey}', {
    api_host: '${POSTHOG_HOST}',
    ui_host: '${POSTHOG_HOST}',
    disable_compression: true,
    loaded: function(posthog) {
      posthog.startSessionRecording();
    }
  });
</script>
`;
}

/**
 * HTMLRewriter handler that injects the snippet before </head>.
 */
class HeadInjector {
  constructor(snippet) {
    this.snippet = snippet;
  }

  element(element) {
    element.prepend(this.snippet, { html: true });
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Skip excluded hosts
    if (EXCLUDED_HOSTS.has(url.hostname)) {
      return fetch(request);
    }

    // Only process GET requests (no need to transform POST/PUT/etc)
    if (request.method !== "GET") {
      return fetch(request);
    }

    // Skip requests that are obviously not HTML based on path extension
    const path = url.pathname;
    if (/\.(js|css|png|jpg|jpeg|gif|svg|ico|woff2?|ttf|eot|webp|avif|mp4|webm|json|xml|txt|map|wasm)$/i.test(path)) {
      return fetch(request);
    }

    const response = await fetch(request);

    // Only inject into HTML responses
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("text/html")) {
      return response;
    }

    // Don't inject into error responses or redirects
    if (response.status < 200 || response.status >= 300) {
      return response;
    }

    const apiKey = env.POSTHOG_API_KEY;
    if (!apiKey) {
      // No API key configured — pass through without injection
      return response;
    }

    const snippet = buildSnippet(apiKey);

    // Use HTMLRewriter to stream-inject before </head>
    return new HTMLRewriter()
      .on("head", new HeadInjector(snippet))
      .transform(response);
  },
};
