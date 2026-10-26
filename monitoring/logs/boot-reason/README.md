# boot-reason

One small pod per node. When a node boots, it logs one line saying how the
last boot ended:

| `reason` | Meaning |
|---|---|
| `clean` | Planned reboot or shutdown. Kubelet stopped the pod first. |
| `unclean` | The node died without shutting down: power loss, a kernel panic, or a hardware reset. |
| `watchdog` | The hardware watchdog reset a hung node. |
| `first-run` | First start on this node, so there's no history yet. |
| `pod-restart` | The pod restarted, but the node didn't reboot. |

For `unclean` and `watchdog`, `previous_boot_last_seen` says when the node was
last alive, to within 30 seconds.

Find it in Grafana (Explore, Loki):

```
{k8s_namespace_name="boot-reason"} |= "boot-reason" | json | reason != "pod-restart"
```

The pod writes a few bytes to `/var/lib/boot-reason` on each node. On Talos,
kubelet stops pods during a planned reboot, which is how the pod knows a reboot
was clean. If a planned reboot ever shows up as `unclean`, kubelet didn't get to
stop the pod.

`unclean` tells you that the node died suddenly, not why. To tell a power or
hardware problem from a software crash, check `talos-system` kernel logs just
before `previous_boot_last_seen` on the Node crash logs dashboard. If there's
nothing there, check the machine's BIOS event log.
