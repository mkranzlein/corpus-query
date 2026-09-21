# Firmware Lifecycle Policy and Version Support Commitments

- **Date:** 2026-06-11
- **Attendees:** Priya, Sofia, Callum, Theo, Elena

## Transcript

[Priya]: We've had this on the list for a few weeks. Customers have started asking, and I want us to have an actual policy rather than answering each request one-off. Sofia, you've drafted something. Walk us through it.
[Sofia]: The draft covers three product lines: MX-3, GX-7, and RV-2. For each line, the policy defines what a major version is versus a minor version, how long each receives active support — meaning bug fixes and security patches — and when a version reaches end-of-life. The structure I'm proposing is: the current major version gets active support. The previous major version gets security patches only for eighteen months after the next major version ships. Anything older than that is end-of-life, meaning no patches, no official support.
[Callum]: That's a reasonable framework. My first question is whether any existing contracts commit us to something different. If we've told a customer they'll have support for version X for a specific duration, this policy can't override that.
[Elena]: I have two contracts that mention firmware support. The Quennick contract says we'll provide 'maintenance releases for the installed firmware version for the duration of the agreement,' which runs through December 2027. The Trellisar contract is vaguer — it says 'reasonable firmware support' without a time definition.
[Callum]: The Quennick language is specific enough that we have an obligation. Whatever policy we publish has to be read against that contract language. Sofia, does the eighteen-month active support window cover the Quennick commitment?
[Sofia]: Quennick is on MX-3 firmware 2.4.1. If we release an MX-3 3.0 — which isn't on my near-term roadmap — the eighteen-month clock would start then. We're nowhere near a major version increment on MX-3. So practically speaking, 2.4.x will be the current and only supported major version for the foreseeable future, which means Quennick is covered.
[Callum]: That's fine for now, but the policy as written could create a conflict if we do release a 3.0 during the Quennick contract period. I'd recommend we add a clause that says contractual support commitments take precedence over the general policy.
[Sofia]: I can add that. It doesn't change the structure, just adds a carve-out.
[Theo]: I want to make sure I understand what I can actually tell customers when they ask. If someone calls and asks whether their version is supported, the answer is: check the policy page, and if your version is the current major version or the previous one and within eighteen months of the next major release, you're supported. Is that right?
[Sofia]: Essentially yes. In practice, for every product we have right now, there's only one active major version, so the answer to almost every customer is simply: yes, your version is supported, here's when we'd tell you otherwise.
[Theo]: What about minor versions within a major? If someone is on 2.4.1 and we release 2.4.2, are we obligated to support 2.4.1 indefinitely or do we expect customers to update?
[Sofia]: The policy as drafted says we support the latest minor release within an active major version. If 2.4.2 is out, we'll help customers upgrade from 2.4.1 but we're not required to patch 2.4.1 independently if the fix is already in 2.4.2.
[Theo]: Some customers can't update on a short timeline. Quennick, for example, has change control processes. A firmware update takes them weeks to approve internally.
[Elena]: That's true. We've had that conversation with them.
[Sofia]: I hear that, but if we commit to patching every minor version indefinitely, I can't sustain it with the team I have. The policy needs to be something I can actually deliver.
[Priya]: What's the middle ground?
[Sofia]: We commit to a minimum thirty-day overlap window after a new minor release before the previous minor is unsupported. That gives customers time to plan their update. Thirty days is short, but Callum said customers with specific contract language are carved out anyway.
[Callum]: That's workable. I'd actually push for sixty days on the overlap, just to reduce the risk of a customer claiming we didn't give them reasonable notice.
[Sofia]: Sixty days is fine. I'll update the draft.
[Theo]: Will there be a public-facing version of this policy or is it internal only?
[Sofia]: My draft is written as an internal document. I assumed we'd publish a simplified version externally.
[Priya]: We need to publish something. Customers are asking because they can't find an answer on the website. Callum, can you review the external-facing version before it goes up?
[Callum]: Yes. I want to see it before publication. The language around 'end-of-life' and 'no support' needs to be precise enough that we're not creating warranty implications we didn't intend.
[Elena]: On the question of notifying customers when a version is approaching end-of-life — what's the proposed notice period?
[Sofia]: The draft says ninety days' advance notice before a version goes end-of-life.
[Elena]: That's not enough for enterprise customers. Some of them have six-month procurement cycles for any system change. I'd want one hundred eighty days.
[Sofia]: One hundred eighty days means I have to know six months in advance when I'm going to release a major version. That's hard to commit to on a small team.
[Elena]: Can we do one hundred twenty days as a compromise?
[Sofia]: I can live with one hundred twenty.
[Priya]: One hundred twenty days for end-of-life notice. That goes in the policy. What about the RV-2 — it's a new product. Does this policy apply from day one?
[Sofia]: Yes. The RV-2 is launching on 1.0.0. The policy applies immediately. There's no previous major version, so effectively everything goes into the active support bucket for now.
[Callum]: One thing I want to flag: if we publish this policy, we should make sure it's not incorporated by reference into future contracts without us intending it. I've seen companies get into trouble because a contract says 'subject to vendor's published support policy' and then the policy changes. I'd recommend we version the policy document and ensure contracts reference a specific version or include explicit terms rather than a blanket reference.
[Priya]: Good point. Elena, can you make sure Jamal knows not to reference the support policy URL in contract language without checking with Callum first?
[Elena]: I'll brief Jamal and make it a standard check in our contract review process.
[Theo]: I have one more question for the record. If a customer is on an end-of-life firmware version and they have a defect — not a contract customer, just a standard terms customer — what's our obligation?
[Callum]: Under standard terms, our warranty obligation runs for twelve months from shipment and covers defects in workmanship. A firmware defect in an end-of-life version — if we've given proper notice — would generally be outside warranty if the warranty period has also passed. If the warranty is still active, we'd have to address it regardless of the firmware lifecycle policy.
[Theo]: So a customer who bought a unit six months ago and is on an end-of-life firmware version — we'd still patch them if the firmware defect emerged within the warranty window?
[Callum]: Correct. The lifecycle policy governs ongoing support, not warranty remedies. They're separate.
[Priya]: I think we have enough to finalize the policy. Sofia, you've got the amendments: contractual carve-out language, sixty-day minor version overlap, one hundred twenty-day end-of-life notice. Update the draft and circulate it to everyone in this meeting for final review. Callum, once you've reviewed the external version, we'll publish.
[Sofia]: I'll have the revised internal draft circulated by end of next week.
[Callum]: And I'll turn around my review within five business days of receiving it.

## Decisions

- Firmware lifecycle policy framework adopted: current major version receives active support; previous major version receives security patches only for eighteen months after the next major release; anything older is end-of-life.
- Contractual support commitments take precedence over the general policy; a carve-out clause will be added.
- Minor version overlap window set at sixty days before previous minor version becomes unsupported.
- End-of-life advance notice period set at one hundred twenty days.
- Policy will be versioned; contracts must not reference the policy URL as a blanket incorporation without Callum's review.
- Callum will review the external-facing policy version before publication.

## Action items

- **Sofia:** Update the firmware lifecycle policy draft to include the contractual carve-out, sixty-day minor version overlap, and one-hundred-twenty-day end-of-life notice period, and circulate to all meeting attendees by end of next week.
- **Callum:** Review the external-facing version of the firmware lifecycle policy within five business days of receipt and approve it for publication.
- **Elena:** Brief Jamal on the requirement to not reference the support policy URL in contract language without first checking with Callum.
