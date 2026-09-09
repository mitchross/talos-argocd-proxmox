#!/bin/sh
set -eu

temporal_command() {
  timeout -k 5 30 temporal --disable-config-file \
    --address "${TEMPORAL_ADDRESS}" \
    --namespace "${TEMPORAL_NAMESPACE}" "$@"
}

api="https://${KUBERNETES_SERVICE_HOST}:${KUBERNETES_SERVICE_PORT_HTTPS}"
token="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)"
ca=/var/run/secrets/kubernetes.io/serviceaccount/ca.crt
namespace_json="$(SSL_CERT_FILE="${ca}" timeout -k 5 30 wget -qO- -T 10 \
  --header="Authorization: Bearer ${token}" \
  "${api}/api/v1/namespaces/${POD_NAMESPACE}")"
namespace_uid="$(printf '%s' "${namespace_json}" | \
  sed -n 's/.*"uid"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
test -n "${namespace_uid}"

desired_identity="${CONTROLLER_IDENTITY}/${namespace_uid}"
# Capture before parsing: a pipeline to sed hides a failed or timed-out CLI.
deployments_json="$(temporal_command worker deployment list -o json)"
deployment_names="$(printf '%s' "${deployments_json}" | \
  sed -n 's/^  "name": "\([^"]*\)",$/\1/p')"

printf '%s\n' "${deployment_names}" | while IFS= read -r deployment_name; do
  test -n "${deployment_name}" || continue
  deployment_json="$(temporal_command worker deployment describe --name "${deployment_name}" -o json)"
  manager_identity="$(printf '%s' "${deployment_json}" | \
    sed -n 's/^  "managerIdentity": "\([^"]*\)"$/\1/p')"

  case "${manager_identity}" in
    "${CONTROLLER_IDENTITY}"/*)
      if [ "${manager_identity}" != "${desired_identity}" ]; then
        temporal_command \
          --identity "${manager_identity}" \
          worker deployment manager-identity unset \
          --deployment-name "${deployment_name}" -y
        echo "cleared stale controller identity for ${deployment_name}"
      fi
      ;;
  esac
done
