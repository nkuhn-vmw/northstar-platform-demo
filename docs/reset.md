# Reset and cleanup

Use the original local profile and its `.state/` journal. Verify `cf target` first. Cleanup operates on recorded GUIDs and ownership labels in that exact installation, not on a name prefix alone.

```sh
bin/demo --config my-foundation.local.json cleanup --phase 4 --json
# Inspect the preview, then remove owned apps/routes/bindings:
bin/demo --config my-foundation.local.json cleanup --phase 4 --apply
```

Service instances and their data are preserved by default. `reset --apply` removes owned application resources and redeploys the chosen phase while retaining services. A cumulative downgrade requires an explicit reset.

To delete the owned services and their data too, preview with `--delete-data`, inspect the list, then repeat with `--apply`. This includes native memory and stored credentials; the action is destructive.

The lifecycle refuses unowned attachments, replaced GUIDs or shared routes. It can recover a resource created immediately before an interrupted journal write when the owner and target identity still match. If the journal is lost, stop and have an operator review the resources; do not recreate an owner token or delete by prefix.

Do not simply disable Hub while its resources remain installed. Clean up using the original profile, or deploy a separate prefix. The kit does not revoke upstream Hub registrations or user grants; revoke those through your identity provider/Hub administration when retiring the installation.
