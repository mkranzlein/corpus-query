# CE Mark Certification Scope — RV-2 and GX-7

- **Date:** 2026-02-17
- **Attendees:** Priya, Callum, Marcus, Sofia

## Transcript

[Priya]: Callum, you asked for this meeting. Give us the background.
[Callum]: Two of our prospective customers in continental Europe — Pellowdine Industrial and Fenstad Systems — have both asked, independently, whether our products carry CE marking. We don't have it on the GX-7 or the RV-2. That's been fine for our North American accounts, but it's a hard requirement for distribution in the EU and for sale into certain regulated-environment applications even in the UK under UKCA. I want to understand what the certification scope looks like, what it costs, and what timeline we're talking about.
[Priya]: Are Pellowdine and Fenstad near-term real opportunities or is this exploratory?
[Callum]: Elena tells me Pellowdine is a twelve-to-eighteen month sales cycle and Fenstad is more like six to nine months. So Fenstad is the more urgent driver if we decide to pursue it.
[Marcus]: Which directives are we talking about? CE isn't a single certification — it's a declaration of conformity against applicable directives. For hardware like ours, the usual suspects are the Low Voltage Directive, the EMC Directive, and depending on what the product does, possibly the Radio Equipment Directive if there's wireless involved.
[Callum]: That's exactly the question. What directives apply?
[Marcus]: GX-7 has no wireless. It's wired Ethernet and RS-485. So Radio Equipment Directive almost certainly doesn't apply. We'd be looking at LVD and EMC. RV-2 also has no wireless in the current rev C design. Same two directives.
[Sofia]: There's also RoHS. I know that's a separate regulation, not a directive in the CE sense, but customers often ask about it in the same breath. Are we compliant?
[Marcus]: Our BOM has been RoHS-targeted from the start. I don't have a formal declaration in place, but I believe we're compliant. We'd need to do the documentation work to back that up formally.
[Callum]: Let's add RoHS documentation to the scope of this exercise. Even if it's not technically part of CE, having the declaration ready saves us a separate conversation with customers.
[Priya]: Marcus, what does the CE testing process actually look like for these products? I want to understand the mechanics.
[Marcus]: For EMC and LVD, we engage a notified body or a third-party test lab — they don't have to be the same entity, but usually easier if they are. We submit the product, technical documentation, and a draft Declaration of Conformity. They run the tests — conducted emissions, radiated emissions, immunity, and for LVD, the safety review. If we pass, we get a test report, we issue the DoC ourselves, and we affix the CE mark. The lab doesn't issue the mark; we do, based on the test results.
[Callum]: And if we fail?
[Marcus]: We remediate and retest. Remediation could be a firmware change, a filter component, a shielding modification. Retest costs are usually lower than the initial run if the scope is narrow.
[Callum]: What's the realistic cost to get both products through, assuming a clean first pass?
[Marcus]: For EMC and LVD together, a reputable lab charges somewhere between $8,000 and $14,000 per product. Call it $22,000 to $28,000 for both, plus internal engineering time to prepare the technical file — probably 40 to 60 hours of my time and some of Sofia's for the firmware documentation portions.
[Sofia]: Firmware documentation for CE — what does that involve specifically?
[Marcus]: The technical file needs to describe the software in terms of its safety-relevant behavior. For LVD, that mostly means documenting what the firmware does if the hardware detects an overvoltage or overcurrent condition. It's not a source code audit, but it does need to be specific.
[Sofia]: I can write that. It's probably a two-day effort per product if I'm doing it properly.
[Callum]: Timeline. If we start the lab engagement next month, when do we realistically have CE marking on the RV-2?
[Marcus]: Lab scheduling is the long pole. Good labs book out six to eight weeks for a first slot. If we engage in March, first available test slot might be late April or early May. Testing itself is two to three days. Report turnaround is two to four weeks after that. Realistically, CE on the RV-2 is a July outcome if everything goes well.
[Priya]: The RV-2 ships in June. So CE won't be in place for the initial launch.
[Marcus]: Correct. It can't be, on that timeline.
[Callum]: That's fine for the North American first-wave customers. But we should not promise CE to Fenstad on any timeline shorter than Q3, and even that is optimistic.
[Priya]: Agreed. I don't want to promise something we can't deliver. Callum, can we flag the CE status on the product page in a way that doesn't imply we have it but doesn't scare off prospective EU customers?
[Callum]: Yes. Something like 'CE certification in progress' or 'CE marking planned for Q3 2026' is accurate and not misleading, as long as we're actually pursuing it. I'd want to review whatever language Nadia uses before it goes live.
[Priya]: Nadia isn't in this meeting but I'll loop her in. Marcus, do we need to do anything to the GX-7 hardware before we can submit it for testing?
[Marcus]: I want to do a pre-compliance scan before we commit to a full lab run. We have access to a local EMC pre-scan facility — it's not a certified lab, but it flags obvious issues. I'd want to run both products through that first. Cost is about $1,200 per product, and turnaround is usually one week.
[Priya]: Do it. That's a cheap insurance policy against a failed first test.
[Callum]: One more item: once we have CE, the Declaration of Conformity has to be kept on file and available to market surveillance authorities for ten years. I need to make sure we have a document retention process that covers it.
[Marcus]: I can set that up in our engineering document management system. It's just a folder with access controls and a retention flag.
[Callum]: Good. I'd also like to review the DoC before we issue it. It's a legal declaration and I want to sign off on the language.
[Priya]: That's a reasonable ask. Marcus, build that into the process.
[Marcus]: Will do.

## Decisions

- CE certification will be pursued for both the RV-2 and GX-7, covering the Low Voltage Directive and EMC Directive.
- RoHS documentation will be prepared alongside the CE work.
- Marcus will run both products through a pre-compliance EMC scan before engaging a certified test lab.
- CE marking on the RV-2 is not expected before Q3 2026 and will not be promised to Fenstad Systems on a shorter timeline.
- Callum will review the Declaration of Conformity language before it is issued.
- Any CE-related language on the product page must be reviewed by Callum before it goes live.

## Action items

- **Marcus:** Schedule and run pre-compliance EMC scans on both the RV-2 and GX-7 at the local pre-scan facility.
- **Marcus:** Begin engaging a certified test lab to understand availability and formally book a test slot for the RV-2 starting in March.
- **Sofia:** Draft the firmware safety-behavior documentation for the CE technical file for both products, approximately two days of effort per product.
- **Callum:** Review and approve CE-related product page language with Nadia before it is published.
- **Marcus:** Set up a document retention folder in the engineering document management system for the CE Declaration of Conformity with a ten-year retention flag.
