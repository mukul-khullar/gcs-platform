# Contracts (source of truth)

Rules: SI units on the wire, MAVLink-native NED/FRD, every frame carries
`t_wall_ms` and `t_boot_ms`, altitude names state the datum (`alt_msl_m`,
`alt_rel_m`, `alt_agl_m`), every frame has `sysid`, envelope field `v` for versioning.

Changes need approval from every consumer and a version bump.
Tag: contracts-v1.0 when frozen.
