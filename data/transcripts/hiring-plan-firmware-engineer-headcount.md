# Hiring Plan – Firmware Engineer Headcount

- **Date:** 2026-05-19
- **Attendees:** Priya, Marcus, Sofia, Renata

## Transcript

[Priya]: Marcus, you put this on the calendar so take it away.
[Marcus]: Thanks. The short version is that Sofia and I are underwater and it's been getting worse since January. We shipped the FieldSense 200 firmware, we've been dealing with the Brannock situation, we have the IEC 62443 security work on the plate, and we have two new sensor variants in the product roadmap that are supposed to start firmware development in Q3. I can't do all of that with one firmware engineer. I need to hire at least one more, and honestly I think the right number is two.
[Sofia]: I want to back that up with something concrete. I tracked my time for the last four weeks. About forty percent of my time is going to support-related work — bug triage, customer diagnostic logs, field issue response. That's not what a firmware engineer should be spending nearly half their time on. If we had another person, I could hand off a lot of that and focus on development.
[Priya]: Is the support load a permanent feature or is it elevated right now because of the Brannock issue and the FieldSense launch?
[Sofia]: Honestly, some of both. The Brannock situation added maybe fifteen percent on top of the baseline. But even at baseline, I'm spending twenty-five percent of my time on support-adjacent work. That's been true for the better part of a year.
[Marcus]: And that's not going to get better as we add more products in the field. More units shipped means more support surface area. The trend is in the wrong direction.
[Renata]: What's the fully loaded cost of a firmware engineer at the level you'd be hiring? I want to make sure I'm working with the right number.
[Marcus]: For a mid-level engineer with three to five years of embedded systems experience, I'd expect a base salary in the range of a hundred and fifteen to a hundred and thirty thousand. Fully loaded with benefits and overhead, call it a hundred and sixty to a hundred and eighty thousand per head.
[Renata]: So two hires is potentially three hundred and sixty thousand in annualized cost. That's not trivial. The current headcount budget for engineering has one open slot, which was approved in the annual plan. A second slot would need to go back to the board as a budget amendment.
[Priya]: How quickly do we need the first person?
[Marcus]: Yesterday, honestly. If we post now and move fast, we're probably looking at a September start date for someone good. That's five months away. Every month we wait is another month of Sofia being stretched thin and roadmap work getting pushed.
[Sofia]: I want to flag that if the IEC 62443 work ramps up in Q3 the way it looks like it will, I'm not going to be able to do the security implementation work and keep up with the new sensor firmware development at the same time. Something will slip. I'd rather be honest about that now.
[Priya]: I appreciate you saying that directly. Marcus, if we can only get approval for one hire right now, how do you prioritize — someone who can take development load off Sofia, or someone who can own the security implementation?
[Marcus]: Development generalist first. The security work has some external consultant support budgeted, so we have a partial backstop there. But there's no backstop for the core firmware development work. If that slips, the product roadmap slips.
[Renata]: For the board amendment on a second hire, what's the business case? I need something more than 'we're busy.' I need to be able to show that the cost of not hiring is higher than the cost of hiring.
[Marcus]: The two sensor variants in Q3 — the XT-11 and the pressure-temperature combo unit — those are projected to generate what in year-one revenue, Priya?
[Priya]: Combined, the forecast is about two point four million in year one if we hit the launch dates.
[Marcus]: If we miss the launch dates by two quarters because we don't have the engineering capacity, that's a significant portion of that revenue pushed out. The cost of one additional engineer is a fraction of that. That's the business case.
[Renata]: That's a reasonable argument. I can work with that framing. I'll need Marcus to give me the specific launch dates and the revenue at risk number in writing so I can put it in the amendment request.
[Priya]: Let's do this. We post the first role immediately — that's within the approved budget, no additional approvals needed. Marcus, you own the job description and the hiring process. Renata, you and Marcus work together on the board amendment for the second role. I want that amendment ready to present at the June board meeting.
[Marcus]: Works for me. Can I get HR support for the posting and screening, or is that going to fall on me entirely?
[Priya]: I'll make sure you have support for the administrative side of the process. You shouldn't be doing resume screening yourself.
[Sofia]: One thing I'd ask — can I be involved in the technical interview? I want to make sure whoever we hire can actually work in our codebase, not just pass a generic embedded systems test.
[Marcus]: Absolutely. You'll be the second interviewer on every technical screen.
[Renata]: What's the target start date we should plan the budget around for the second hire, assuming the board approves in June?
[Marcus]: If approval comes in June and we post immediately, realistically October or November for a start date. I'd budget for a November 1st start to be conservative.
[Priya]: Good. Let's move.

## Decisions

- The first firmware engineer hire will be posted immediately using the already-approved headcount budget.
- A board budget amendment will be prepared for a second firmware engineer hire, to be presented at the June board meeting.
- Sofia will participate as the second interviewer in all technical screens for the firmware engineer role.

## Action items

- **Marcus:** Write the job description for the firmware engineer role and initiate the posting process.
- **Marcus:** Provide Renata with specific Q3 product launch dates and associated revenue-at-risk figures for the board budget amendment.
- **Renata:** Prepare the board budget amendment for the second firmware engineer headcount, targeting the June board meeting.
