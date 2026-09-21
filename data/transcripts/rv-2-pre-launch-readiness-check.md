# RV-2 Pre-Launch Readiness Check

- **Date:** 2026-05-19
- **Attendees:** Priya, Marcus, Sofia, Devon, Elena, Nadia, Theo

## Transcript

[Priya]: We're five weeks from the RV-2 ship date. The point of this meeting is to surface anything that's going to stop us from hitting that date or embarrass us with first customers. I want to go around the table. Marcus, hardware first.
[Marcus]: Hardware is in good shape. Rev C boards passed all electrical qualification. We had two minor issues during thermal cycling — one component on the power rail that we've since confirmed was a handling defect from the test fixture, not a design issue, and a pad delamination on two boards out of the thirty-unit qual lot that we traced to a reflow profile setting at the contract manufacturer. Both are resolved. Yield on the qual lot was 93.3%, which is actually better than we projected at this stage.
[Devon]: I want to add some context to that yield number. The 93.3% is on a thirty-unit hand-built qual lot. Production tooling isn't fully dialed in yet. When we move to the full production run, I'd expect yield to be lower initially — maybe 88 to 90% — before the line stabilizes. We've seen that pattern on every product we've built. I don't want Marcus's 93.3% to be the number people are anchoring to for production planning.
[Marcus]: That's a fair point. I should have been clearer. The qual lot yield tells us the design is manufacturable, not that we'll see that yield on day one of production.
[Priya]: Devon, at 88% yield, what does that do to our first-run delivery commitment?
[Devon]: We've got a 400-unit first run scheduled. At 88% yield, that's 352 good units. We have 310 units committed to first-wave customers, so we have some buffer. If yield drops below 77.5%, we're in trouble on commitments. I don't expect that, but I want it named.
[Priya]: Okay. Sofia, firmware.
[Sofia]: Firmware 1.0.0 release candidate went into soak on Monday. We're running it on twelve units in the lab, mix of thermal conditions, continuous operation. So far, seventy-two hours in, no faults. We've got a checklist of forty-one test scenarios and we're through thirty-four of them. The remaining seven are the longer-duration scenarios — idle-period behavior, edge cases on the communications stack under load. I expect to be done by end of this week, and if nothing unexpected comes up, I'm confident calling 1.0.0 ready for ship by next Friday.
[Priya]: What are the odds something unexpected comes up?
[Sofia]: I can't put a number on it. The architecture is simpler than the MX-3 was at this stage, the test coverage is better, and we haven't had a surprise in the last three weeks of development. I feel good about it, but I won't say zero risk.
[Theo]: Can I ask — what's the OTA update path if something does come up after units are in customer hands? Is that infrastructure ready?
[Sofia]: Yes. OTA is built in from the start on RV-2, unlike the MX-3 where we retrofitted it. We can push a signed update to any connected unit. The only gap is units that aren't network-connected at the time of a push, but we have a fallback USB update path for those.
[Theo]: Good, that's what I needed to know. On the support side, I've got documentation drafted for the most likely first-call issues based on what Marcus and Sofia flagged as known edge cases. The internal knowledge base has twelve articles ready. I want to add two more before launch — one on the USB update path Sofia just mentioned, and one on network configuration for customers who aren't using DHCP. I didn't realize the static IP setup was going to be as involved as it is.
[Marcus]: I can get you a write-up on the static IP configuration by Thursday. That one caught us by surprise in lab too.
[Theo]: That works.
[Nadia]: From a marketing standpoint, campaign assets are final. Press release is written and embargoed with three contacts. The product page goes live the morning of ship day. We've got a launch email going to the full prospect list — Elena, that's about 1,400 names — and a separate email to existing customers that leads with the upgrade angle. One thing I want to flag: the introductory pricing we've been building toward in the campaign is $179. That's the number in the press release draft, it's the number in the product page, and it's the number I've verbally mentioned to the press contacts. I need to confirm that's still the number we're shipping with.
[Elena]: It's $189. We settled on $189 as the intro price.
[Nadia]: I have $179 in every piece of campaign material I've built. When did that change?
[Elena]: It didn't change, as far as I know. I thought $189 was always the number.
[Nadia]: I don't — okay, I'm not going to relitigate this right now, but one of us is working from the wrong number and we need to resolve it before anything goes out. Priya, do you remember what was decided?
[Priya]: I believe it was $189. But Nadia, if your materials say $179, we need to figure out where that came from and make sure we're aligned before the press release goes anywhere. Can you two get on a call today and sort it out?
[Nadia]: Yes. Elena, can we do thirty minutes after this?
[Elena]: Yes.
[Priya]: Good. That has to be resolved today. What's the step-up price after the intro window?
[Elena]: $209.
[Nadia]: That part I have right.
[Devon]: I want to come back to schedule for a second. The 400-unit first run starts on June 2nd at the contract manufacturer. That's locked. What's not locked is whether we're shipping firmware on the units at the CM or doing a post-receipt flash here. Sofia, where did that land?
[Sofia]: If 1.0.0 is released by next Friday, the CM can flash at the line. We'd send them the signed image and the flash procedure. If for any reason firmware isn't released by then, we do post-receipt flash in-house, which adds probably four to five days to the fulfillment timeline.
[Devon]: Four to five days puts us right at the edge of the ship date commitment. I'd rather know by end of this week whether we're flashing at the CM or not, so I can give the CM a definitive procedure.
[Sofia]: I'll have a go or no-go answer for you by Friday at noon.
[Devon]: That works.
[Priya]: Theo, anything else on the support side before we close out?
[Theo]: Two things. One: what's the warranty period on RV-2? I don't have that in the documentation yet. Two: we don't have a returns process defined for the first wave. With MX-3 we had an RMA flow before launch and it saved us a lot of scrambling. I'd like to get that in place for RV-2 before the first units ship.
[Priya]: Warranty period is twelve months, same as GX-7. That's in the standard terms. For the RMA flow, Devon, can you and Theo align on that this week?
[Devon]: Yes, we can do that.
[Theo]: Good. I'll send Devon a draft of the MX-3 RMA process as a starting point.
[Priya]: Is there anything that would make us recommend slipping the ship date? I want to go around the table on that one explicit question. Marcus?
[Marcus]: No. Hardware is ready.
[Devon]: No slip from me, assuming the CM run starts June 2nd as planned.
[Sofia]: No slip, assuming soak testing finishes clean this week. If something surfaces in the remaining seven scenarios I'll flag it immediately.
[Elena]: No slip from sales. Customers are expecting this date.
[Nadia]: No slip from marketing, once we get the pricing sorted.
[Theo]: No slip, as long as I get the RMA process and the warranty language before first units go out.
[Priya]: Good. We stay on schedule. Nadia and Elena, sort out the intro price today. Everyone else, your action items are what you said they were. Let's talk again if anything breaks loose before June.

## Decisions

- RV-2 remains on track for the current ship date; no slip recommended by any function.
- Sofia will provide a go or no-go on CM-line firmware flashing by Friday noon; if not released in time, post-receipt flash in-house will be used as fallback.
- RV-2 warranty period is twelve months, consistent with standard product terms.
- Nadia and Elena will resolve the introductory price discrepancy today before any press or campaign materials are distributed.

## Action items

- **Sofia:** Complete remaining seven soak test scenarios and deliver a go or no-go decision on firmware 1.0.0 readiness by Friday noon.
- **Marcus:** Send Theo a write-up on the static IP network configuration edge case by Thursday.
- **Theo:** Add a USB update path article and a static IP configuration article to the support knowledge base before launch.
- **Devon:** Align with Theo on the RV-2 RMA process this week, using the prior product's process as a starting point.
- **Nadia:** Resolve the introductory price discrepancy with Elena today and update all campaign materials to reflect the confirmed price before any press release is distributed.
