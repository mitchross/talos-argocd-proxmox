# Keep alert view

Alertmanager sends events to Keep. Critical alerts do not automatically call
Holmes or the local model. `backend.provision.workflows` is deliberately empty;
Holmes remains parked until explicitly enabled for an investigation.

The chart includes a workflow checksum in the backend pod template, so changing
the provisioned list rolls the backend. Keep 0.52.1 removes previously provisioned
workflows at startup when no workflows directory or inline workflow is configured.
See its [provisioning code](https://github.com/keephq/keep/blob/v0.52.1/keep/workflowmanager/workflowstore.py)
and [provisioning guide](https://docs.keephq.dev/deployment/provision/workflow).

After sync, check that the backend rollout completes and `holmes-rca` is absent
from the workflow list. Confirm alerts still arrive. This removes the automatic
trigger; it does not deploy the Holmes console or add an investigation interface.
A Git revert restores the workflow and automatic critical-alert calls.
