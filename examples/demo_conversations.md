# Demo conversation scripts

These scripts exercise the expected session behavior. The local vehicle API uses a mock snapshot based on the sample payload from the project specification; do not treat the values as live vehicle data.

## 1. Location not updating → vehicle intake

**User:** My GPS location is not updating.

**Assistant:** I can check the tracker status. What is the vehicle number as it appears in TrackoBit? For example: `HR85G2799`.

**User:** `HR85G2799`

**Expected:** The sample vehicle payload is loaded. Because its example `state` is `Ignition off` and its last update is stale relative to runtime, the assistant asks the user to move the vehicle and switch ignition on before declaring a hardware fault.

## 2. Answer a side question and resume

**User:** My vehicle location is not updating.

**Assistant:** asks for vehicle number.

**User:** `HR85G2799`

**Assistant:** continues with mock vehicle status / asks to move the vehicle if ignition is off.

**User:** How do I create a geofence?

**Expected:** The current diagnosis pauses. With the knowledge folder empty, the assistant says it cannot find an approved article rather than inventing product-specific steps, and reminds the user where the GPS workflow paused.

**User:** Continue.

**Expected:** The chat resumes from the exact stored `paused_at_step` rather than starting over.

## 3. Device command output entered as text

When a hardware diagnosis reaches a command step, the assistant asks for the configured command and screenshot. In demo mode, paste output like `GPS: fixed, GSM: 1, GPRS: disconnected, Battery: 3.8V` if screenshot vision is not enabled. The rule engine should detect weak GSM and/or server disconnection from configured Concox V5 rules.
