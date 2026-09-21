# Support Backlog and Escalation Triage — MX-3 and GX-7

- **Date:** 2026-03-26
- **Attendees:** Theo, Elena, Sofia, Devon

## Transcript

[Theo]: I asked for this because the backlog has gotten to a point where I can't triage it alone and a few things need decisions from people who aren't me. As of this morning I have 23 open tickets across MX-3 and GX-7. Fourteen are minor — configuration questions, documentation gaps, stuff I can close without involving anyone. Nine are substantive.
[Elena]: Which customers are in the nine?
[Theo]: Quennick has three open. Trellisar has two. Hessanby Dynamics has two — they're new to the platform and both of theirs are setup-related, so I'm not worried about those. And then there are two from Ivelmoor Group that have been open longer than I'm comfortable with.
[Elena]: Ivelmoor. What are those?
[Theo]: First one is a GX-7 unit that's reporting intermittent communication timeouts on the RS-485 bus. Customer says it started after they reorganized their panel wiring about six weeks ago. I've been working them through cable length and termination checks but we haven't resolved it. Second one is a firmware question — they asked whether the GX-7 supports a specific register read interval shorter than 500 milliseconds, and I don't have a definitive answer.
[Sofia]: On the register read interval — what's the specific interval they're asking about?
[Theo]: They want 200 milliseconds.
[Sofia]: The firmware scheduler runs at 250-millisecond resolution in the current release. 200 milliseconds is not achievable without a firmware change. I can give you a written answer for the ticket.
[Theo]: That would help. Can you get it to me today?
[Sofia]: Yes. I'll write it up so you can send it verbatim.
[Theo]: The RS-485 timeout issue — Devon, is there anything on the hardware side I should be walking them through that I might be missing? I've covered termination resistors and cable length. What else?
[Devon]: Ground potential difference is the one that bites people after a rewire. If they moved cables and crossed panel sections, the ground reference between the GX-7 and the downstream device might have shifted. Ask them to measure the ground voltage between the GX-7 chassis and the RS-485 device chassis with a meter. If it's more than a couple of volts, that's your problem.
[Theo]: I would not have thought of that. I'll add it to the ticket today.
[Elena]: Ivelmoor is a $90,000 account. I'd like both of those tickets closed before end of next week. Theo, will that be possible?
[Theo]: With Sofia's answer on the register question, yes, that one closes fast. The RS-485 issue depends on how quickly Ivelmoor's team can do the ground check. I'll push for it.
[Elena]: Let me know if you need me to make a call to their project lead. I'd rather involve myself early than have it escalate.
[Theo]: I'll try the technical path first. If Ivelmoor doesn't respond by Thursday, I'll flag you.
[Elena]: Good. What about the Quennick tickets?
[Theo]: Two of the three are related. Quennick has MX-3 units in a facility where ambient temperature runs high — they said up to 48 degrees Celsius in summer. They're asking whether the MX-3 is rated for that and whether there are any operational limitations they should know about.
[Devon]: The MX-3 is rated to 55 degrees Celsius operating, so 48 is within spec. But I'd want to flag that sustained operation above 45 degrees will shorten capacitor life on the power board — it's within spec but it's toward the top of the comfortable range. I'd recommend they ensure airflow around the unit.
[Theo]: Is there documentation I can send them or do I need to write something up?
[Devon]: The operating temperature range is in the datasheet. The capacitor life guidance isn't written down anywhere formal. I can put together a short application note — probably a page — that covers high-temperature deployment recommendations.
[Theo]: That would be very useful, not just for Quennick but for any customer in a hot environment. Can you have it in two weeks?
[Devon]: Two weeks is fine.
[Theo]: Quennick's third ticket is actually a firmware question. They're asking whether MX-3 firmware 2.4.1 will be supported past end of year or whether they need to plan an upgrade. Sofia, do we have a published support lifecycle for firmware versions?
[Sofia]: We don't have a published policy. Internally, I've been maintaining 2.4.x with patches as needed, but I haven't committed to a public end-of-life date. That's a policy question, not a technical one.
[Elena]: Quennick will not accept 'we don't have a policy' as an answer. They have procurement and IT governance requirements. They need something in writing.
[Theo]: What should I tell them in the meantime?
[Elena]: Tell them we're formalizing the lifecycle policy and will have a written commitment to them within thirty days. That buys us time without closing a door.
[Theo]: I can send that. Sofia, can you actually have a draft lifecycle policy ready in that window?
[Sofia]: A draft, yes. Whether it goes through Priya and Callum and gets approved in thirty days — that I can't promise.
[Elena]: Let's start the clock anyway. If it slips, I'll manage Quennick.
[Theo]: Trellisar — their two tickets are both GX-7. One is a question about whether we support Modbus TCP in addition to RTU. The other is a hardware thing: they say one of their units has a status LED that's dimmer than the others. Not off, just noticeably dimmer.
[Sofia]: Modbus TCP — the GX-7 supports RTU only in the current firmware. TCP is on the roadmap but I can't commit to a release date.
[Devon]: The dim LED could be a resistor tolerance issue on that specific unit, or it could be the LED itself. It's cosmetic — it doesn't affect function. If Trellisar wants a replacement unit, we should just swap it and take the return.
[Theo]: They haven't asked for a replacement. They just reported it. Should I proactively offer one?
[Elena]: Yes. Offer it. It costs us one unit and it signals that we stand behind the hardware. Trellisar is a growth account.
[Devon]: I can pull a replacement from finished goods stock and have it shipped this week if Theo sends me the request.
[Theo]: Done. I'll send you the shipping details today.
[Elena]: How many GX-7 units do we have in finished goods right now, by the way?
[Devon]: As of Monday's count, 34 units.
[Theo]: Last thing — I want to flag a pattern I'm seeing. Seven of my 23 tickets involve questions that should be answerable from the documentation but aren't, because the docs are incomplete or outdated. Static IP configuration, Modbus register maps, operating environment specs. I'm spending time answering questions that the manual should handle. I'm not sure what the fix is, but someone should know it's happening.
[Elena]: That's a real cost. Every ticket Theo answers manually is time not spent on new customers.
[Devon]: The register map I can update — I have a current version that never made it into the customer-facing docs. I'll get it to Theo.
[Sofia]: I can do the same for the firmware-related sections. Give me a list of what's missing, Theo, and I'll prioritize it.
[Theo]: I'll pull together a gap list from the tickets and send it to both of you by end of week.

## Decisions

- Elena will contact Ivelmoor's project lead if Theo has not received a response on the RS-485 issue by Thursday.
- Quennick will be told that a formal firmware lifecycle policy will be provided in writing within thirty days.
- A replacement GX-7 unit will be proactively offered to Trellisar for the dim LED issue and shipped this week.

## Action items

- **Sofia:** Write up a definitive answer on the GX-7 200ms register read interval limitation for Theo to send to Ivelmoor today.
- **Theo:** Add the ground potential difference troubleshooting step to the Ivelmoor RS-485 timeout ticket.
- **Devon:** Write a one-page high-temperature deployment application note for the MX-3 within two weeks.
- **Sofia:** Draft a firmware version lifecycle and support policy within thirty days for Priya and Callum to review.
- **Theo:** Send Devon the Trellisar shipping details today so the replacement GX-7 unit can be dispatched this week.
- **Devon:** Send Theo the current GX-7 Modbus register map for inclusion in customer-facing documentation.
- **Theo:** Compile a documentation gap list from open tickets and send it to Sofia and Devon by end of week.
