# RenderBob Blender Plugin Release Checklist

## Compatibility matrix

- [ ] Blender `4.2.x` on macOS (Apple Silicon)
- [ ] Blender `4.2.x` on macOS (Intel)
- [ ] Blender `4.2.x` on Windows 11
- [ ] Blender `4.2.x` on Ubuntu 22.04+

## Functional QA

- [ ] API token verify/logout works (`/api/v1/users/me`)
- [ ] Account refresh loads credits + server list (`/billing/credits`, `/renders/servers`)
- [ ] Preflight and readiness checks catch invalid scenes
- [ ] Multipart upload works for small and large `.blend` files
- [ ] Upload cancel aborts multipart upload cleanly
- [ ] Draft and publish flow succeeds
- [ ] Poll and auto-poll show progress updates
- [ ] Terminate and retry-launch controls behave correctly
- [ ] Estimate/pay/cancel/status billing flow works
- [ ] Outputs list/file download/zip workflow works

## Reliability checks

- [ ] Resume after temporary network loss
- [ ] Handle 401 (expired/revoked token) with clear user message
- [ ] Handle 429 throttling with retry guidance
- [ ] Handle 5xx errors without addon crash

## Security checks

- [ ] Token never appears in URLs/query strings
- [ ] Token storage path permissions are user-local only
- [ ] TLS validation remains enabled

## Packaging and release

- [ ] `python3 -m compileall renderbob_plugin` passes
- [ ] `./scripts/package-addon.sh` generates `dist/renderbob-addon.zip`
- [ ] Install packaged zip in clean Blender profile
- [ ] Update addon version in `blender_manifest.toml` and `bl_info`
