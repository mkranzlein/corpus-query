# RV-2 Firmware 1.0.0 Go/No-Go Decision

- **Date:** 2026-05-22
- **Attendees:** Priya, Marcus, Sofia, Devon

## Transcript

[Priya]: Let's get straight to it. Sofia, where are we on the release candidate?
[Sofia]: Soak testing completed at eleven this morning. Seventy-two hours on six units, no faults, no watchdog trips, no unexpected reboots. Nominal current draw throughout. I'm calling it go from a firmware standpoint.
[Priya]: Any open items from the test matrix?
[Sofia]: One marginal result on the thermal stress cycle — unit four hit a slightly elevated core temp reading at the top of the range, 81 degrees against a 75-degree typical. It resolved on its own within the cycle and did not repeat. I do not believe it's a firmware issue; it looks like a board-level thermal path variation on that specific unit. I flagged it to Marcus.
[Marcus]: I looked at it. That unit had a slightly proud component on the main thermal pad — it's a placement tolerance issue, not a design defect. We've seen it before on rev B. Devon, has the contract manufacturer tightened that tolerance on the rev C pick-and-place program?
[Devon]: Yes, it was in the rev C ECO package. The CM confirmed it in writing two weeks ago. That specific unit in soak was from the qual lot, which was built before the ECO landed. Production units will have the corrected placement spec.
[Marcus]: Then I'm satisfied. The thermal observation doesn't hold the firmware release.
[Priya]: Good. Devon, what does a go decision today mean for the manufacturing timeline?
[Devon]: If we cut the release today, I can get the firmware image to the CM by end of day. Their line flash setup is already staged — they've been waiting on us. The 400-unit run starts Monday. Units come off line Tuesday afternoon, pack-out Wednesday, freight pickup Thursday morning.
[Priya]: That hits the June second ship date?
[Devon]: Comfortably. We have a full day of buffer before the freight cutoff.
[Priya]: What's the alternative if we had called no-go today?
[Devon]: We flash in-house after receipt. That's a four-to-five day operation with the team we have. It would push first-wave fulfillment to June ninth at the earliest, which puts us outside the committed window for three of the seven accounts.
[Sofia]: We're not in that scenario. The build is clean.
[Priya]: Agreed. Marcus, any hardware holds from your side?
[Marcus]: None. Electrical qual passed, the ECO is in, BOM is locked. I have nothing that blocks a go.
[Priya]: Then we're go. Sofia, cut the release and get the image to Devon. Devon, you get it to the CM today.
[Sofia]: Will do. I'll tag the repo and generate the release artifact within the hour.
[Devon]: Send it to the CM shared drive and copy me. I'll confirm receipt with them by three o'clock.
[Priya]: One more thing. The version that ships — is it still labeled 1.0.0?
[Sofia]: Yes. The release candidate promoted cleanly. No patches, no hotfixes. It ships as 1.0.0.
[Priya]: Good. I want that on the product page before we announce. Nadia should have it by end of day. I'll send her a note.
[Marcus]: Do we have a field update path documented for customers who want to verify the version on their units?
[Sofia]: The version string is exposed over the local API on port 8080 — GET /status returns it in the firmware_version field. I'll write that up for Theo's support documentation so he can tell customers how to check it.
[Priya]: Perfect. Let's close it out.

## Decisions

- Firmware 1.0.0 is approved for release; the go decision is confirmed.
- Sofia will cut the release and deliver the image to Devon today for same-day transmission to the contract manufacturer.
- The production run proceeds as scheduled for a June 2nd ship date.

## Action items

- **Sofia:** Tag the repository, generate the 1.0.0 release artifact, and deliver the firmware image to Devon within the hour.
- **Devon:** Transmit the firmware image to the contract manufacturer by 3 PM today and confirm receipt.
- **Sofia:** Write up the firmware version verification procedure (GET /status on port 8080) for Theo's support documentation.
