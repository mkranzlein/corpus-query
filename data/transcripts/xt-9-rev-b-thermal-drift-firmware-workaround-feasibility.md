# XT-9 Rev B Thermal Drift – Firmware Workaround Feasibility

- **Date:** 2026-03-05
- **Attendees:** Marcus, Sofia, Devon

## Transcript

[Marcus]: I wanted to get the three of us together before this gets any wider. We've had two separate field reports in the past month — different accounts, different installations — where XT-9 units are showing analog output drift at elevated ambient temperatures. Both sites run process lines that can get into the high fifties Celsius in summer. The pattern is consistent enough that I think we have a real problem with the Rev B analog output stage.
[Sofia]: I've been looking at the hardware design. The voltage reference on the analog output stage has a tempco that starts to matter above about 55 degrees. Rev B used the cheaper reference component — the Talcott VR-220. Rev C swapped in the VR-240, which has a much flatter tempco curve, and that's why we haven't seen this on Rev C units.
[Devon]: How many Rev B units are still in the field? Do we have a number on that?
[Marcus]: Our best estimate is somewhere around 340 units shipped on Rev B. Not all of them are in high-temperature environments, but we don't have precise installation data for most of them.
[Sofia]: So the question I've been sitting with is whether we can do anything in firmware to compensate for the thermal drift. Conceptually yes — if we add a temperature compensation lookup table and the unit has an onboard temperature sensor reading that we can trust, we could apply a correction coefficient to the analog output. The XT-9 does have the onboard thermal sensor, so the data is theoretically available.
[Marcus]: What's your confidence level on that actually solving the problem versus just reducing it?
[Sofia]: Honest answer: it would reduce it, probably significantly, but it won't fully cancel the drift. The VR-220's tempco isn't perfectly linear, so a lookup table can get you most of the way there but there will still be residual error at the extremes. At 60 degrees, I'd estimate we could get the output error down from maybe plus-or-minus 1.8% to plus-or-minus 0.4 or 0.5%. Whether that's acceptable depends on what the customer's process actually requires.
[Devon]: What's the spec on the XT-9 for output accuracy?
[Sofia]: Plus-or-minus 0.3%.
[Devon]: So even with the firmware fix we'd still be out of spec at high temperature.
[Sofia]: Technically yes. In the worst case at the top of the temperature range, we would be.
[Marcus]: That's the part that worries me. If we push a firmware update and tell customers it fixes the problem, and then someone's process has an incident because we're still out of spec, that's a much worse position to be in than if we'd been upfront about the hardware limitation.
[Devon]: Is there a way to do the firmware update but also be transparent that it's a partial mitigation and not a full fix? Like, document it properly?
[Marcus]: That's one option. The other option is we don't offer a firmware workaround at all and instead focus entirely on a hardware replacement path — swap Rev B for Rev C wherever the unit is operating above 50 degrees ambient.
[Sofia]: The firmware update is probably two weeks of work to do properly. Testing on the bench across the temperature range, validation, writing the update documentation. If we're going to do it, I'd want to do it right.
[Marcus]: What would a Rev C swap program cost us? Devon, do you have any sense of the unit cost on Rev C versus Rev B?
[Devon]: Rev C BOM is running about $6 more per unit than Rev B was. If we're talking about a proactive swap for units in hot environments, we'd need to figure out which of those 340 units those are, which we mostly don't know. And then there's the logistics cost — shipping, field labor if we're doing on-site swaps.
[Marcus]: I think realistically we can't do a proactive swap for all 340. What we can do is have Rev C replacement units available for any customer who reports the issue and be ready to respond fast.
[Sofia]: Could we do both? Ship the firmware update to all Rev B units in the field as a general improvement, describe it accurately as a thermal compensation enhancement, and then have the hardware replacement ready for any site that's actually experiencing problems?
[Marcus]: That might be the right middle path. The firmware update buys time and goodwill, the hardware replacement is there for the cases where it matters. But I want Callum to look at any customer-facing language before we send anything out. I don't want to inadvertently admit a defect in a way that creates liability exposure.
[Devon]: Makes sense. Should we also think about whether Rev B should still be the version we're shipping for any open orders?
[Marcus]: We shouldn't be shipping Rev B for new orders. Are we?
[Devon]: I want to double-check, but I believe we have a handful of units in finished goods inventory that are Rev B. Probably 20 to 25 units. We built them before Rev C tooling was fully qualified.
[Marcus]: Those should not ship. I'll flag that to you as a formal hold — can you pull those from available inventory today?
[Devon]: Yes, I'll do that this afternoon.
[Sofia]: Do we want to set a target date for the firmware update? Two weeks is my estimate, but that assumes it's my primary focus and I'm not pulled onto other things.
[Marcus]: Make it your primary focus. I'd rather have this done in two weeks than have it drag to four because other things keep interrupting. If something else comes up that threatens to pull you off it, tell me immediately.
[Sofia]: Understood. I'll have a draft ready for bench testing by March 19th.
[Marcus]: Good. I'll set up a quick check-in the week of March 16th so we know where we stand before the testing phase.

## Decisions

- Sofia will develop a firmware thermal compensation update for XT-9 Rev B units as a partial mitigation, targeted for bench testing by March 19th.
- Rev B finished goods inventory (estimated 20–25 units) will be placed on hold immediately and will not ship for new orders.
- A hardware replacement path using Rev C units will be maintained for customers actively experiencing the drift issue.
- Any customer-facing communications about the firmware update must be reviewed by Callum before distribution.

## Action items

- **Devon:** Pull all Rev B finished goods units from available inventory today and place them on hold.
- **Sofia:** Develop and bench-test the XT-9 firmware thermal compensation update, targeting a draft ready for testing by March 19th.
- **Marcus:** Engage Callum to review customer-facing language for the firmware update communications before anything is sent externally.
