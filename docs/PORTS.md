# NAS host-port registry

A running list of **host ports** claimed by self-hosted services on the Synology
NAS, so new containers don't collide. Only the host (left) side of a Docker
`host:container` mapping has to be unique — container-internal ports can repeat.

**Update this whenever you add, move, or retire a service.**

| Host port | Service | Container port | Notes |
|-----------|---------|----------------|-------|
| 5000 / 5001 | Synology DSM | — | Default admin UI (http / https) |
| 8043 / 8843 | Omada Controller | — | HTTPS mgmt / HTTPS portal (part of the Omada cluster) |
| 8088 | Omada Controller | — | HTTP management portal |
| 8123 | Flight Tracker | 8080 | `ghcr.io/brspencer90/flight-tracker` |
| **8124** | **Mileage Tracker** | **8000** | `ghcr.io/brspencer90/mileage-tracker` (this project) |

Omada also reserves several high ports for device discovery/adoption
(e.g. 27001, 29810–29816) — avoid those too when picking a new host port.

Convention: keep app containers clustered in the 812x range (flightTracker 8123,
mileageTracker 8124, …) so they're easy to remember and stay clear of Omada/DSM.
