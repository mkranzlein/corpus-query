# Quennick Escalation — Firmware Defect on MX-3 Units

- **Date:** 2026-04-09
- **Attendees:** Priya, Sofia, Theo, Elena, Callum

## Transcript

[Priya]: Theo, you flagged this yesterday afternoon. Walk everyone through what Quennick reported.
[Theo]: So Quennick's field team started seeing units go into a fault state after what they're describing as an extended idle period. Not on every unit, not on a predictable schedule. They've got eleven confirmed cases across the batch of three hundred and twelve units we shipped them in February. The units aren't bricked — they come back after a power cycle — but Quennick's use case doesn't allow for manual intervention in the field. So a unit that needs a power cycle is effectively a failed unit for them.
[Elena]: I heard from their procurement lead this morning. She was not calm about it. They're asking whether this is a known defect and whether the entire batch is affected.
[Priya]: Sofia, you've been looking at the logs Quennick sent over. What's your read?
[Sofia]: The logs point pretty clearly to a watchdog timer issue in the idle management routine. There's a race condition that can occur when the unit has been idle for more than roughly four hours and then receives a certain class of interrupt. The watchdog fires before the interrupt handler completes, and the unit faults. It's not random — it's deterministic once you know the trigger — but the trigger depends on what's happening on their network, which is why they're seeing it inconsistently.
[Priya]: Is this in the firmware version we shipped to everyone, or just Quennick?
[Sofia]: It's in 2.4.1, which is what the February batch shipped with. Quennick is the only customer running units in a deployment pattern that would reliably hit this trigger. Most of our other customers cycle their units more frequently. But the bug is in the firmware. Any unit on 2.4.1 is technically vulnerable.
[Theo]: That's the part that worries me. We have four other customers on MX-3 hardware. If any of them hits the right conditions, we'll see the same thing.
[Elena]: How quickly can we get a fix out?
[Sofia]: I have a patch written. I've been testing it since last night. The fix is straightforward — I'm extending the watchdog window and adding a guard in the interrupt handler. I want to run it through another twelve hours of soak testing before I'd call it ready for release, but I could have a candidate build by tomorrow evening.
[Callum]: Before we talk about what we're telling Quennick, I want to understand the exposure. Eleven units have faulted. Is there any risk to their downstream systems when a unit faults? Any data loss, any connected equipment that could be affected?
[Sofia]: The fault is a clean shutdown. The unit stops processing and holds its last state. There's no data corruption, no output to connected equipment. It just stops.
[Callum]: And their contract — Elena, what does the warranty language look like for software defects? Do we have a response time commitment?
[Elena]: The Quennick contract has a severity-one response time of forty-eight hours for defects that cause operational impact. We're inside that window right now, but just barely. We need to have something substantive to tell them today.
[Callum]: What's the remedy clause? Are we obligated to replace units or is a firmware update sufficient?
[Elena]: It says 'repair or replace at vendor's discretion.' A firmware update should qualify as repair, but I'd want Callum to confirm that reading.
[Callum]: I'll pull the contract and look at the specific language. My initial read is that a firmware update would qualify, but I want to be sure before we commit to that position with the customer.
[Priya]: Okay. What do we tell Quennick today?
[Theo]: I think we have to acknowledge that we've identified the root cause. Telling them we're still investigating when we know what it is would be a problem if it came out later.
[Elena]: I agree. I'd rather get ahead of it. But how do we frame the scope? Do we tell them it's a firmware issue that could affect other customers too, or do we keep that internal for now?
[Callum]: We shouldn't say anything misleading about scope. If they ask whether other customers are affected, we shouldn't deny it. But we don't need to volunteer the full picture in the opening communication. We should say we've identified the cause, we have a fix in testing, and we'll deliver it within a defined timeframe.
[Priya]: Sofia, what's a realistic commitment on the patch delivery?
[Sofia]: If testing goes cleanly tonight, I can have a release candidate ready by tomorrow at five. I'd want Devon's team to do a quick sanity check on the build pipeline before we push it, but that's a few hours, not a day.
[Theo]: So we could realistically tell Quennick they'll have a firmware update by end of day Friday?
[Sofia]: That's tight but doable if nothing unexpected comes up in soak testing.
[Priya]: What's the install process for Quennick? Can they push the update remotely or does someone have to go on site?
[Theo]: Their units are on our OTA update channel. We push the firmware, their units pull it on the next check-in cycle, which happens every six hours. No one needs to go on site. The eleven faulted units will need a manual power cycle first, but after that they'll be on the update channel.
[Elena]: Do we know how many of those eleven units Quennick can physically access to do the power cycle? Some of them are in pretty remote locations.
[Theo]: I don't have that information. I'd have to ask their field team.
[Priya]: That's a good question for the call with them today. Okay — here's what I want to happen. Theo and Elena, you're on the Quennick call this afternoon. You acknowledge root cause identified, fix in testing, update delivery by end of day Friday. Callum, you review the contract language and tell Elena before that call whether the firmware update satisfies our remedy obligation. Sofia, you keep the soak test running and flag me immediately if anything unexpected turns up. I also want us to think about the other four MX-3 customers. We don't wait for them to hit the bug.
[Theo]: Agreed. I can draft a proactive notice to the other customers — something that tells them we've identified a firmware issue and that an update is coming, without causing panic.
[Sofia]: I'd suggest we also push the update to them on the same timeline. No reason to treat them differently.
[Priya]: Do that. One firmware release, all MX-3 customers on 2.4.1 get it simultaneously.
[Callum]: For the other customers, is there a notification obligation in their contracts? Some agreements require advance notice before we push firmware.
[Elena]: Varies by customer. I'll check the other four contracts and flag anything that requires advance notice.
[Priya]: Good. Callum, add that to your review. I want to know before we push anything.
[Callum]: On it.
[Priya]: One more thing. How did 2.4.1 go out with this in it? I'm not looking to assign blame right now, but I want to understand the gap in our test coverage so we close it.
[Sofia]: Honestly, the idle-period trigger wasn't in our standard test matrix. We test idle behavior, but not at four-plus hours with the specific interrupt class that causes the race. It's a gap. I'll write up what we should add to the regression suite.
[Priya]: Please do. That's a process fix, not just a bug fix.

## Decisions

- Quennick to be informed today that root cause has been identified and a firmware update will be delivered by end of day Friday.
- Firmware patch 2.4.2 to be pushed to all MX-3 customers on 2.4.1 simultaneously, subject to contract notification review.
- Sofia to add idle-period interrupt scenarios to the standard regression test matrix.

## Action items

- **Callum:** Review Quennick contract to confirm firmware update satisfies the repair-or-replace remedy obligation, and check all other MX-3 customer contracts for advance-notice requirements before firmware push.
- **Sofia:** Complete soak testing and deliver firmware release candidate 2.4.2 by end of day Friday, and write up additions to the regression test matrix.
- **Theo:** Lead the Quennick call this afternoon and draft proactive notice to other MX-3 customers on 2.4.1.
- **Elena:** Join the Quennick call and provide contract context on remedy and response-time commitments.
