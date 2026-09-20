# Customer Escalation – Brannock Refinery Account

- **Date:** 2026-04-08
- **Attendees:** Elena, Jamal, Theo, Marcus

## Transcript

[Elena]: Okay so the reason this is happening right now instead of at the end of the week is that I got a call from Brannock's operations director this morning and it was not a friendly call. They're saying three of the XT-9 units we shipped in February are giving erratic readings and they've had to take two process lines offline as a precaution. They want someone on-site by Thursday.
[Theo]: I've been tracking this one. The first ticket came in March 18th — unit serial BRN-0042 was showing intermittent dropout on the analog output. We walked them through a recalibration and they said it was resolved. Then a second ticket came in March 31st for a different unit, BRN-0067, same symptom. And then this morning they opened a third ticket for BRN-0091 before Elena's call even came in.
[Jamal]: I spoke to their procurement lead last week about a renewal and she didn't mention any of this. I feel like I've been caught off-blind here.
[Elena]: Their procurement and operations teams don't talk to each other well. That's not unusual for a site that size. The point is we have a problem now.
[Marcus]: Can Theo pull the diagnostic logs from those three units? If they submitted them through the support portal we should have the raw data.
[Theo]: BRN-0042 and BRN-0067 both have logs uploaded. BRN-0091 just opened this morning so there's nothing yet. I looked at the logs from the first two last week and I flagged them to you, Marcus — did you get that?
[Marcus]: I did get it. I looked at them briefly but I hadn't gotten to a full analysis. That's on me. Looking at it now — the dropout pattern in both units is happening at roughly the same ambient temperature range, above about 58 degrees Celsius. That's within the rated operating range but it's in the upper portion.
[Elena]: Is this a firmware issue or a hardware issue?
[Marcus]: I can't say definitively without more data. The analog output stage has a known thermal sensitivity that we addressed in the Rev C hardware. I need to check what revision Brannock's units are.
[Theo]: I can check the serial number manifest. Give me one second. Okay — all three units shipped to Brannock are Rev B.
[Marcus]: That's the issue. Rev B has the thermal drift problem on the analog output. We released Rev C specifically to address that. The fix is a component change on the output stage, it's not something you can patch in firmware.
[Elena]: So we shipped them hardware we knew had a problem?
[Marcus]: We shipped them hardware that was within spec at the time of shipment. The Rev B units are rated to 60 degrees Celsius and they're operating at 58. The problem is that the spec was too generous — Rev C tightened the effective thermal range because we found in field data that the margin wasn't what we thought. I wouldn't say we knowingly shipped defective units.
[Elena]: Brannock's operations director is not going to find that distinction comforting.
[Jamal]: How many Rev B units do we have in the field total? Is this just Brannock or are there other accounts running hot environments?
[Marcus]: I don't have that number off the top of my head. I'd need to cross-reference the shipping manifest against the hardware revision log. It's not a five-minute job.
[Theo]: I can pull the support ticket history for any other accounts that have reported analog output issues. That might give us a faster proxy for who else could be affected.
[Elena]: Do that. But right now I need to figure out what we're telling Brannock and whether someone is getting on a plane. Marcus, can you go on-site Thursday?
[Marcus]: I can go Thursday. I want to bring replacement units — Rev C — and do a swap on all three affected units while I'm there. If they'll let me, I'd also want to do a site survey to check the actual ambient temperatures in the sensor locations, because 58 degrees is what they're reporting but I want to verify.
[Elena]: I'll call the operations director back and tell him we're sending our head of hardware engineering personally, we're bringing replacement units, and we're going to make this right. Is there any reason I shouldn't make that commitment?
[Marcus]: No, make the commitment. I'll need Devon to pull three Rev C units from inventory and get them to me by Wednesday afternoon.
[Theo]: Should I keep the three tickets open or merge them into a single escalation record?
[Elena]: Merge them into a single escalation and flag it as a priority one. I want everything in one place when Marcus is on-site.
[Theo]: Done. I'll also draft a brief summary of the ticket history so Marcus has context before he walks in the door.
[Jamal]: What do I tell the procurement lead about the renewal? The timing is terrible.
[Elena]: Tell her nothing yet. Let Marcus go on-site, let us fix the problem, and then we have a conversation about the renewal from a position of having resolved the issue rather than having it hanging over us. If she calls you before Thursday, be warm, be honest that there's a technical issue being addressed, and don't make any commitments.
[Jamal]: Understood. Do we know if there's any liability exposure here — the two process lines they've taken offline, is that something Callum should look at?
[Elena]: Good call. I'll loop Callum in after this call. I want to know what our contract with Brannock says about consequential damages before anyone puts anything in writing to them.
[Marcus]: One more thing — if the site survey shows that ambient temperatures in those sensor locations are regularly above 55 degrees, we may need to have a conversation with Brannock about whether the XT-9 is the right sensor for that environment, even with Rev C hardware. I don't want to replace the units and then have the same problem come back.
[Elena]: Let's solve Thursday first and have that conversation after we have the site data.

## Decisions

- Marcus will travel on-site to Brannock Refinery on Thursday with three Rev C replacement units to swap the affected Rev B units.
- The three open support tickets for Brannock will be merged into a single priority-one escalation record.
- Callum will be looped in to review the Brannock contract for consequential damages language before any written commitments are made.
- Jamal will not discuss the renewal with Brannock procurement until the technical issue is resolved.

## Action items

- **Marcus:** Travel to Brannock Refinery on Thursday, replace the three Rev B units with Rev C hardware, and conduct a site survey of ambient temperatures at sensor locations.
- **Theo:** Merge the three Brannock tickets into a single priority-one escalation and prepare a ticket history summary for Marcus before Thursday.
- **Theo:** Pull support ticket history for all other accounts to identify any other potential Rev B units in high-temperature environments.
- **Elena:** Call Brannock's operations director to confirm Marcus's on-site visit and replacement unit commitment, and loop in Callum on the contract review.
